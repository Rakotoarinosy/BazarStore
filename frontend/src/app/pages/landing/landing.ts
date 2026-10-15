import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { HttpClient, HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { Router, RouterModule } from '@angular/router';
import { EMPTY, catchError, finalize } from 'rxjs';
import { MessageService } from 'primeng/api';
import { ToastModule } from 'primeng/toast';
import { AuthService } from '../../core/auth/auth.service';
import { CartItem, CartStore } from '../../core/cart/cart.store';
import { CatalogProduct, ProductCatalogStore } from '../../core/products/product-catalog.store';
import { SseClient } from '../../core/realtime/sse-client';
import { RandomOrder } from '../../shared/random-order';
import { ScrollTopButton } from '../../shared/scroll-top/scroll-top-button';

interface StorefrontOrderStatus {
    id: string;
    status: string;
}

interface ShoppingMissionRecommendation {
    product: CatalogProduct;
    reason: string;
}

interface ShoppingMissionResult {
    mission: string;
    budget: number;
    total_price: number;
    summary: string;
    recommendations: ShoppingMissionRecommendation[];
}

@Component({
    selector: 'app-landing',
    standalone: true,
    imports: [RouterModule, ToastModule, ScrollTopButton],
    templateUrl: './landing.html',
    styleUrl: './landing.css',
    providers: [MessageService]
})
export class Landing {
    private readonly http = inject(HttpClient);
    private readonly router = inject(Router);
    private readonly sse = inject(SseClient);
    private readonly destroyRef = inject(DestroyRef);
    readonly catalog = inject(ProductCatalogStore);
    readonly cart = inject(CartStore);
    readonly auth = inject(AuthService);
    private readonly myOrders = signal<StorefrontOrderStatus[]>([]);
    readonly pendingOrdersCount = computed(() => this.myOrders().filter((order) => order.status !== 'completed').length);
    private readonly messages = inject(MessageService);
    private readonly visitorId = this.getOrCreateVisitorId();
    readonly heroMainImage = signal<string | null>(null);
    readonly heroSecondaryImage = signal<string | null>(null);

    readonly currentYear = new Date().getFullYear();
    searchTerm = '';
    selectedCategory = '';
    selectedProduct: CatalogProduct | null = null;
    favoriteIds = new Set<string>();
    favoriteBusyIds = new Set<string>();
    favoritesLoaded = false;
    cartOpen = false;
    orderSubmitting = false;
    // Signaux : mis à jour depuis la réponse HTTP, que le mode zoneless ne suit pas seul.
    readonly newsletterEmail = signal('');
    readonly newsletterStatus = signal<'idle' | 'sending' | 'success' | 'error'>('idle');
    readonly subscriptionMessage = signal('');
    readonly missionIdeas = ['Reprendre le sport', 'Trouver un cadeau', 'Améliorer mon quotidien'];
    readonly missionText = signal('');
    readonly missionBudget = signal(300_000);
    readonly missionLoading = signal(false);
    readonly missionResult = signal<ShoppingMissionResult | null>(null);
    readonly missionError = signal('');
    readonly missionCartMessage = signal('');
    loggingOut = false;
    categoryDisplayCount = 6;
    private readonly categoryPageSize = 6;
    // « Tout voir » est mélangé à chaque visite ; les catégories restent alphabétiques.
    private readonly randomOrder = new RandomOrder();

    constructor() {
        this.loadFavoriteIds();
        this.catalog.load(true).subscribe();
        this.http.get<{ hero_main_image_url: string | null; hero_secondary_image_url: string | null }>('/api/v1/storefront/settings').subscribe({
            next: (settings) => {
                this.heroMainImage.set(settings.hero_main_image_url);
                this.heroSecondaryImage.set(settings.hero_secondary_image_url);
            }
        });
        // Restaure la session depuis le cookie HttpOnly après un rechargement.
        this.auth
            .refresh()
            .pipe(
                takeUntilDestroyed(this.destroyRef),
                catchError(() => {
                    this.auth.clearSession();
                    return EMPTY;
                })
            )
            .subscribe(() => this.loadPendingOrdersCount());
    }

    private loadPendingOrdersCount(): void {
        if (!this.auth.currentUser()) return;

        this.http.get<StorefrontOrderStatus[]>('/api/v1/orders/mine').pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
            next: (orders) => this.myOrders.set(orders)
        });

        this.sse
            .stream('/api/v1/orders/mine/stream')
            .pipe(takeUntilDestroyed(this.destroyRef))
            .subscribe((message) => {
                if (message.event !== 'order') return;
                const updated = JSON.parse(message.data) as StorefrontOrderStatus;
                this.myOrders.update((orders) =>
                    orders.some((order) => order.id === updated.id)
                        ? orders.map((order) => order.id === updated.id ? updated : order)
                        : [updated, ...orders]
                );
            });
    }

    logout(): void {
        if (this.loggingOut) return;

        this.loggingOut = true;
        this.auth
            .logout()
            .pipe(
                catchError(() => EMPTY),
                finalize(() => {
                    this.loggingOut = false;
                    void this.router.navigateByUrl('/auth/login');
                })
            )
            .subscribe();
    }

    get filteredProducts() {
        const search = this.searchTerm.trim().toLocaleLowerCase();

        const products = this.catalog.products().filter((product) => {
            const matchesCategory = !this.selectedCategory || product.category_id === this.selectedCategory;
            const matchesSearch =
                !search || `${product.name} ${product.category_name} ${product.description}`.toLocaleLowerCase().includes(search);

            return matchesCategory && matchesSearch;
        });

        return (this.selectedCategory ? products : this.randomOrder.sort(products)).slice(0, 12);
    }

    get visibleCategories() {
        return this.catalog.categories();
    }

    get selectedCategoryInfo() {
        return this.catalog.categories().find((category) => category.id === this.selectedCategory);
    }

    get displayedCategories() {
        return this.visibleCategories.slice(0, this.categoryDisplayCount);
    }

    get hiddenCategoryCount(): number {
        return Math.max(0, this.visibleCategories.length - this.categoryDisplayCount);
    }

    get hasExpandedCategoryList(): boolean {
        return this.categoryDisplayCount > this.categoryPageSize;
    }

    get categoryExpandLabel(): string {
        if (!this.hiddenCategoryCount) return 'Réduire la liste';
        const amount = Math.min(this.hiddenCategoryCount, this.categoryPageSize);
        return `Afficher ${amount} catégorie${amount > 1 ? 's' : ''} de plus`;
    }

    categoryProductCount(categoryId: string): number {
        return this.catalog.products().filter((product) => product.category_id === categoryId).length;
    }

    toggleAllCategories(): void {
        this.categoryDisplayCount = this.hiddenCategoryCount > 0
            ? Math.min(this.categoryDisplayCount + this.categoryPageSize, this.visibleCategories.length)
            : this.categoryPageSize;
    }

    get showBackofficeLink(): boolean {
        return ['admin', 'commercial', 'manager'].includes(this.auth.currentUser()?.role ?? '');
    }

    get cartItems(): CartItem[] {
        return this.cart.items();
    }

    get cartTotal(): number {
        return this.cart.total();
    }

    get cartItemCount(): number {
        return this.cart.count();
    }

    formatPrice(price: number | undefined): string {
        return `${new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 }).format(price ?? 0)} Ar`;
    }

    updateSearch(event: Event): void {
        if (event.target instanceof HTMLInputElement) {
            this.searchTerm = event.target.value;
        }
    }

    updateMissionText(event: Event): void {
        if (event.target instanceof HTMLTextAreaElement) {
            this.missionText.set(event.target.value);
            this.missionError.set('');
            this.missionResult.set(null);
        }
    }

    updateMissionBudget(event: Event): void {
        if (!(event.target instanceof HTMLInputElement)) return;
        const budget = Number(event.target.value);
        if (Number.isInteger(budget) && budget > 0 && budget <= 100_000_000) {
            this.missionBudget.set(budget);
            this.missionError.set('');
            this.missionResult.set(null);
        }
    }

    chooseMission(idea: string): void {
        this.missionText.set(idea);
        this.missionError.set('');
        this.missionResult.set(null);
    }

    requestMission(event: Event): void {
        event.preventDefault();
        const mission = this.missionText().trim();
        const budget = this.missionBudget();
        if (mission.length < 5 || this.missionLoading()) return;

        this.missionLoading.set(true);
        this.missionError.set('');
        this.missionResult.set(null);
        this.missionCartMessage.set('');
        this.http
            .post<ShoppingMissionResult>('/api/v1/shopping-missions/recommendations', { mission, budget })
            .pipe(
                takeUntilDestroyed(this.destroyRef),
                catchError((error: HttpErrorResponse) => {
                    this.missionError.set(
                        error.status === 503
                            ? error.error?.detail ?? 'Le conseiller est momentanément indisponible.'
                            : 'Impossible de préparer cette sélection. Vérifiez votre mission et votre budget.'
                    );
                    return EMPTY;
                }),
                finalize(() => this.missionLoading.set(false))
            )
            .subscribe((result) => this.missionResult.set(result));
    }

    addMissionRecommendationsToCart(): void {
        const result = this.missionResult();
        if (!result?.recommendations.length) return;
        result.recommendations.forEach(({ product }) => this.cart.add(product));
        this.missionResult.set(null);
        this.missionError.set('');
        this.missionCartMessage.set('');
        this.cartOpen = true;
    }

    handleLandingAnchorClick(event: MouseEvent): void {
        if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        if (!(event.target instanceof Element)) return;

        const anchor = event.target.closest<HTMLAnchorElement>('a[href^="#"]');
        if (!anchor || anchor.target === '_blank') return;

        const hash = anchor.getAttribute('href');
        if (!hash || hash === '#') return;

        const target = document.getElementById(decodeURIComponent(hash.slice(1)));
        if (!target) return;

        event.preventDefault();
        if (window.location.hash !== hash) window.history.pushState(null, '', hash);
        target.scrollIntoView({
            behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
            block: 'start'
        });
    }

    selectCategory(category: string): void {
        this.selectedCategory = category;
        document.getElementById('products')?.scrollIntoView({
            behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
            block: 'start'
        });
    }

    openProductDetails(product: CatalogProduct): void {
        this.cartOpen = false;
        this.selectedProduct = product;
    }

    closeProductDetails(): void {
        this.selectedProduct = null;
    }

    addSelectedProductToCart(): void {
        if (!this.selectedProduct) return;
        this.addToCart(this.selectedProduct);
        this.closeProductDetails();
    }

    categoryProduct(categoryId: string): CatalogProduct | undefined {
        return this.catalog.products().find((product) => product.category_id === categoryId && product.image_url);
    }

    toggleFavorite(productId: string | undefined): void {
        if (!productId || this.favoriteBusyIds.has(productId)) return;

        const wasFavorite = this.favoriteIds.has(productId);
        const nextFavorites = new Set(this.favoriteIds);
        if (wasFavorite) nextFavorites.delete(productId);
        else nextFavorites.add(productId);
        this.favoriteIds = nextFavorites;
        this.favoriteBusyIds = new Set(this.favoriteBusyIds).add(productId);

        const request = wasFavorite
            ? this.http.delete<void>(`/api/v1/reactions/products/${productId}`, { headers: this.visitorHeaders() })
            : this.http.put<void>(`/api/v1/reactions/products/${productId}`, {}, { headers: this.visitorHeaders() });
        request.subscribe({
            next: () => this.finishFavoriteRequest(productId),
            error: () => {
                const restoredFavorites = new Set(this.favoriteIds);
                if (wasFavorite) restoredFavorites.add(productId);
                else restoredFavorites.delete(productId);
                this.favoriteIds = restoredFavorites;
                this.finishFavoriteRequest(productId);
                this.messages.add({
                    severity: 'error',
                    summary: 'Favori non enregistré',
                    detail: 'Vérifiez votre connexion et réessayez.',
                    life: 3500
                });
            }
        });
    }

    isFavorite(productId: string | undefined): boolean {
        return productId ? this.favoriteIds.has(productId) : false;
    }

    private loadFavoriteIds(): void {
        this.http.get<string[]>('/api/v1/reactions/mine', { headers: this.visitorHeaders() }).subscribe({
            next: (productIds) => {
                this.favoriteIds = new Set(productIds);
                this.favoritesLoaded = true;
            },
            error: () => this.favoritesLoaded = true
        });
    }

    private finishFavoriteRequest(productId: string): void {
        const busyIds = new Set(this.favoriteBusyIds);
        busyIds.delete(productId);
        this.favoriteBusyIds = busyIds;
    }

    private visitorHeaders(): HttpHeaders {
        return new HttpHeaders({ 'X-Visitor-Id': this.visitorId });
    }

    private getOrCreateVisitorId(): string {
        const key = 'bazarstore.visitor-id';
        try {
            const existing = localStorage.getItem(key);
            if (existing && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(existing)) {
                return existing;
            }
            const visitorId = typeof crypto !== 'undefined' && 'randomUUID' in crypto
                ? crypto.randomUUID()
                : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (char) => {
                    const random = Math.floor(Math.random() * 16);
                    return (char === 'x' ? random : (random & 0x3) | 0x8).toString(16);
                });
            localStorage.setItem(key, visitorId);
            return visitorId;
        } catch {
            return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (char) => {
                const random = Math.floor(Math.random() * 16);
                return (char === 'x' ? random : (random & 0x3) | 0x8).toString(16);
            });
        }
    }

    addToCart(product: CatalogProduct): void {
        this.cart.add(product);
        this.messages.add({
            severity: 'success',
            summary: 'Ajouté au panier',
            detail: product.name,
            life: 2200
        });
    }

    changeQuantity(index: number, change: number): void {
        this.cart.changeQuantity(index, change);
    }

    removeFromCart(index: number): void {
        this.cart.remove(index);
    }

    placeOrder(): void {
        if (!this.cartItems.length || this.orderSubmitting) return;

        this.cart.persist();
        this.orderSubmitting = true;
        if (this.auth.currentUser()) {
            this.sendOrder();
            return;
        }

        // A cookie session may still be restoring after the page was opened.
        this.auth.refresh().pipe(catchError(() => EMPTY)).subscribe({
            next: () => this.auth.currentUser() ? this.sendOrder() : this.goToLogin(),
            complete: () => {
                if (!this.auth.currentUser()) this.goToLogin();
            }
        });
    }

    private sendOrder(): void {
        this.http.post('/api/v1/orders', {
            items: this.cartItems.map(({ product, quantity }) => ({ product_id: product.id, quantity }))
        }).pipe(finalize(() => (this.orderSubmitting = false))).subscribe({
            next: () => {
                this.cart.clear();
                this.cartOpen = false;
                void this.router.navigateByUrl('/my-orders');
            },
            error: (error: { error?: { detail?: string } }) => {
                this.messages.add({
                    severity: 'error',
                    summary: 'Commande impossible',
                    detail: error.error?.detail ?? 'Vérifiez le stock et réessayez.',
                    life: 5000
                });
            }
        });
    }

    private goToLogin(): void {
        this.orderSubmitting = false;
        void this.router.navigateByUrl('/auth/login');
    }

    updateNewsletterEmail(event: Event): void {
        if (event.target instanceof HTMLInputElement) {
            this.newsletterEmail.set(event.target.value);
            if (this.newsletterStatus() !== 'sending') this.newsletterStatus.set('idle');
        }
    }

    subscribe(event: Event): void {
        event.preventDefault();
        const email = this.newsletterEmail().trim();
        if (!email || this.newsletterStatus() === 'sending') return;

        this.newsletterStatus.set('sending');
        this.subscriptionMessage.set('');
        this.http
            .post<{ message: string }>('/api/v1/newsletter/subscriptions', { email })
            .pipe(takeUntilDestroyed(this.destroyRef))
            .subscribe({
                next: ({ message }) => {
                    this.newsletterEmail.set('');
                    this.newsletterStatus.set('success');
                    this.subscriptionMessage.set(message);
                },
                error: (error: HttpErrorResponse) => {
                    this.newsletterStatus.set('error');
                    this.subscriptionMessage.set(
                        error.status === 422
                            ? 'Cette adresse e-mail ne semble pas valide.'
                            : 'Inscription momentanément impossible. Réessayez dans quelques instants.'
                    );
                }
            });
    }
}
