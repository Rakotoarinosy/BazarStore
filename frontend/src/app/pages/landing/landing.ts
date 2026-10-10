import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { HttpClient } from '@angular/common/http';
import { Router, RouterModule } from '@angular/router';
import { EMPTY, catchError, finalize } from 'rxjs';
import { MessageService } from 'primeng/api';
import { ToastModule } from 'primeng/toast';
import { AuthService } from '../../core/auth/auth.service';
import { CatalogProduct, ProductCatalogStore } from '../../core/products/product-catalog.store';
import { SseClient } from '../../core/realtime/sse-client';

interface StorefrontOrderStatus {
    id: string;
    status: string;
}

@Component({
    selector: 'app-landing',
    standalone: true,
    imports: [RouterModule, ToastModule],
    templateUrl: './landing.html',
    providers: [MessageService]
})
export class Landing {
    private readonly http = inject(HttpClient);
    private readonly router = inject(Router);
    private readonly sse = inject(SseClient);
    private readonly destroyRef = inject(DestroyRef);
    readonly catalog = inject(ProductCatalogStore);
    readonly auth = inject(AuthService);
    private readonly myOrders = signal<StorefrontOrderStatus[]>([]);
    readonly pendingOrdersCount = computed(() => this.myOrders().filter((order) => order.status !== 'completed').length);
    private readonly messages = inject(MessageService);
    private readonly cartStorageKey = 'bazarstore.pending-cart';
    readonly heroMainImage = signal<string | null>(null);
    readonly heroSecondaryImage = signal<string | null>(null);

    readonly currentYear = new Date().getFullYear();
    searchTerm = '';
    selectedCategory = '';
    cartItems: { product: CatalogProduct; quantity: number }[] = [];
    favoriteIds = new Set<string>();
    cartOpen = false;
    orderSubmitting = false;
    newsletterEmail = '';
    subscriptionMessage = '';
    loggingOut = false;
    categoryDisplayCount = 6;
    private readonly categoryPageSize = 6;

    constructor() {
        this.restoreCart();
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

        return this.catalog.products().filter((product) => {
            const matchesCategory = !this.selectedCategory || product.category_id === this.selectedCategory;
            const matchesSearch =
                !search || `${product.name} ${product.category_name} ${product.description}`.toLocaleLowerCase().includes(search);

            return matchesCategory && matchesSearch;
        }).slice(0, 8);
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

    get cartTotal(): number {
        return this.cartItems.reduce((total, item) => total + (item.product.price ?? 0) * item.quantity, 0);
    }

    get cartItemCount(): number {
        return this.cartItems.length;
    }

    formatPrice(price: number | undefined): string {
        return `${new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 }).format(price ?? 0)} Ar`;
    }

    updateSearch(event: Event): void {
        if (event.target instanceof HTMLInputElement) {
            this.searchTerm = event.target.value;
        }
    }

    selectCategory(category: string): void {
        this.selectedCategory = category;
        document.getElementById('products')?.scrollIntoView({ behavior: 'smooth' });
    }

    categoryProduct(categoryId: string): CatalogProduct | undefined {
        return this.catalog.products().find((product) => product.category_id === categoryId && product.image_url);
    }

    toggleFavorite(productId: string | undefined): void {
        if (!productId) {
            return;
        }

        if (this.favoriteIds.has(productId)) {
            this.favoriteIds.delete(productId);
        } else {
            this.favoriteIds.add(productId);
        }
    }

    isFavorite(productId: string | undefined): boolean {
        return productId ? this.favoriteIds.has(productId) : false;
    }

    addToCart(product: CatalogProduct): void {
        const existing = this.cartItems.find((item) => item.product.id === product.id);
        if (existing) {
            existing.quantity += 1;
            this.cartItems = [...this.cartItems];
        } else {
            this.cartItems = [...this.cartItems, { product, quantity: 1 }];
        }
        this.persistCart();
        this.messages.add({
            severity: 'success',
            summary: 'Ajouté au panier',
            detail: product.name,
            life: 2200
        });
    }

    changeQuantity(index: number, change: number): void {
        const item = this.cartItems[index];
        if (!item) return;

        const quantity = item.quantity + change;
        this.cartItems = quantity > 0
            ? this.cartItems.map((entry, itemIndex) => itemIndex === index ? { ...entry, quantity } : entry)
            : this.cartItems.filter((_, itemIndex) => itemIndex !== index);
        this.persistCart();
    }

    removeFromCart(index: number): void {
        this.cartItems = this.cartItems.filter((_, itemIndex) => itemIndex !== index);
        this.persistCart();
    }

    placeOrder(): void {
        if (!this.cartItems.length || this.orderSubmitting) return;

        this.persistCart();
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
        this.http.post<{ reference: string; total_amount: number }>('/api/v1/orders', {
            items: this.cartItems.map(({ product, quantity }) => ({ product_id: product.id, quantity }))
        }).pipe(finalize(() => (this.orderSubmitting = false))).subscribe({
            next: (order) => {
                this.cartItems = [];
                this.clearPersistedCart();
                this.cartOpen = false;
                this.messages.add({
                    severity: 'success',
                    summary: 'Commande enregistrée',
                    detail: `${order.reference} · ${this.formatPrice(order.total_amount)}`,
                    life: 5000
                });
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

    private restoreCart(): void {
        try {
            const saved = sessionStorage.getItem(this.cartStorageKey);
            if (!saved) return;
            const parsed = JSON.parse(saved) as Array<{ product: CatalogProduct; quantity: number }>;
            this.cartItems = Array.isArray(parsed)
                ? parsed.filter((item) => item?.product?.id && Number.isInteger(item.quantity) && item.quantity > 0)
                : [];
        } catch {
            this.cartItems = [];
        }
    }

    private persistCart(): void {
        try {
            sessionStorage.setItem(this.cartStorageKey, JSON.stringify(this.cartItems));
        } catch {
            // The in-memory cart remains usable if browser storage is unavailable.
        }
    }

    private clearPersistedCart(): void {
        try {
            sessionStorage.removeItem(this.cartStorageKey);
        } catch {
            // The in-memory cart was already cleared.
        }
    }

    updateNewsletterEmail(event: Event): void {
        if (event.target instanceof HTMLInputElement) {
            this.newsletterEmail = event.target.value;
        }
    }

    subscribe(event: Event): void {
        event.preventDefault();
        this.subscriptionMessage = 'La newsletter sera bientôt disponible. Aucune inscription n’a été enregistrée.';
    }
}
