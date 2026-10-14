import { HttpClient, HttpHeaders } from '@angular/common/http';
import { AfterViewInit, Component, DestroyRef, ElementRef, ViewChild, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { CartItem, CartStore } from '../../core/cart/cart.store';
import { CatalogProduct, ProductCatalogStore } from '../../core/products/product-catalog.store';
import { RandomOrder } from '../../shared/random-order';
import { ScrollTopButton } from '../../shared/scroll-top/scroll-top-button';

@Component({
    selector: 'app-catalog-page',
    standalone: true,
    imports: [RouterModule, ScrollTopButton],
    templateUrl: './catalog-page.html',
    styleUrl: './catalog-page.css'
})
export class CatalogPage implements AfterViewInit {
    private readonly http = inject(HttpClient);
    private readonly route = inject(ActivatedRoute);
    private readonly router = inject(Router);
    private readonly destroyRef = inject(DestroyRef);
    private readonly visitorId = this.getVisitorId();
    readonly catalog = inject(ProductCatalogStore);
    readonly cart = inject(CartStore);
    readonly batchSize = 12;
    searchTerm = '';
    selectedCategory = '';
    // Signal : le callback de l'IntersectionObserver s'exécute hors des événements
    // du template, donc en mode zoneless seul un signal déclenche le rendu.
    readonly visibleCount = signal(this.batchSize);
    selectedProduct: CatalogProduct | null = null;
    cartOpen = false;
    notice = '';
    favoriteIds = new Set<string>();
    favoriteBusyIds = new Set<string>();
    favoritesLoaded = false;
    private observer?: IntersectionObserver;
    // « Tout voir » est mélangé à chaque visite ; les catégories restent alphabétiques.
    private readonly randomOrder = new RandomOrder();

    @ViewChild('loadMoreSentinel') private sentinel?: ElementRef<HTMLElement>;

    constructor() {
        this.catalog.load().pipe(takeUntilDestroyed(this.destroyRef)).subscribe();
        this.loadFavorites();
        this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params) => {
            this.selectedCategory = params.get('category') ?? '';
            this.visibleCount.set(this.batchSize);
        });
    }

    ngAfterViewInit(): void {
        if (typeof IntersectionObserver === 'undefined' || !this.sentinel) return;
        this.observer = new IntersectionObserver((entries) => {
            if (entries.some((entry) => entry.isIntersecting)) this.loadMore();
        }, { rootMargin: '320px 0px' });
        this.observer.observe(this.sentinel.nativeElement);
        this.destroyRef.onDestroy(() => this.observer?.disconnect());
    }

    get products(): CatalogProduct[] {
        const search = this.searchTerm.trim().toLocaleLowerCase();
        const products = this.catalog.products().filter((product) => {
            const categoryMatches = !this.selectedCategory || product.category_id === this.selectedCategory;
            const searchMatches = !search || `${product.name} ${product.category_name} ${product.description}`.toLocaleLowerCase().includes(search);
            return categoryMatches && searchMatches;
        });
        return this.selectedCategory ? products : this.randomOrder.sort(products);
    }

    get visibleProducts(): CatalogProduct[] {
        return this.products.slice(0, this.visibleCount());
    }

    get hasMore(): boolean {
        return this.visibleCount() < this.products.length;
    }

    get cartItems(): CartItem[] {
        return this.cart.items();
    }

    get cartItemCount(): number {
        return this.cart.count();
    }

    get cartTotal(): number {
        return this.cart.total();
    }

    get selectedCategoryInfo() {
        return this.catalog.categories().find((category) => category.id === this.selectedCategory);
    }

    setSearch(event: Event): void {
        if (!(event.target instanceof HTMLInputElement)) return;
        this.searchTerm = event.target.value;
        this.resetResults();
    }

    selectCategory(categoryId: string): void {
        this.selectedCategory = categoryId;
        this.resetResults();
        void this.router.navigate([], {
            relativeTo: this.route,
            queryParams: { category: categoryId || null },
            queryParamsHandling: 'merge',
            replaceUrl: true
        });
        document.getElementById('catalog-results')?.scrollIntoView({ behavior: this.scrollBehavior(), block: 'start' });
    }

    loadMore(): void {
        if (!this.hasMore) return;
        this.visibleCount.set(Math.min(this.visibleCount() + this.batchSize, this.products.length));
        // Re-observer le marqueur permet de remplir l'écran si le lot ajouté
        // reste plus court que la zone de préchargement.
        if (this.hasMore && this.observer && this.sentinel) {
            this.observer.unobserve(this.sentinel.nativeElement);
            requestAnimationFrame(() => this.observer?.observe(this.sentinel!.nativeElement));
        }
    }

    formatPrice(price: number): string {
        return `${new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 }).format(price)} Ar`;
    }

    toggleFavorite(product: CatalogProduct): void {
        if (this.favoriteBusyIds.has(product.id)) return;
        const wasFavorite = this.favoriteIds.has(product.id);
        const next = new Set(this.favoriteIds);
        wasFavorite ? next.delete(product.id) : next.add(product.id);
        this.favoriteIds = next;
        this.favoriteBusyIds = new Set(this.favoriteBusyIds).add(product.id);
        const headers = new HttpHeaders({ 'X-Visitor-Id': this.visitorId });
        const request = wasFavorite
            ? this.http.delete<void>(`/api/v1/reactions/products/${product.id}`, { headers })
            : this.http.put<void>(`/api/v1/reactions/products/${product.id}`, {}, { headers });
        request.pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
            next: () => this.finishFavorite(product.id),
            error: () => {
                const restored = new Set(this.favoriteIds);
                wasFavorite ? restored.add(product.id) : restored.delete(product.id);
                this.favoriteIds = restored;
                this.finishFavorite(product.id);
            }
        });
    }

    addToCart(product: CatalogProduct): void {
        this.notice = this.cart.add(product)
            ? `${product.name} ajouté au panier.`
            : 'Le panier est momentanément indisponible.';
    }

    changeQuantity(index: number, change: number): void {
        this.cart.changeQuantity(index, change);
    }

    removeFromCart(index: number): void {
        this.cart.remove(index);
    }

    private resetResults(): void {
        this.visibleCount.set(this.batchSize);
        this.notice = '';
        if (this.observer && this.sentinel) {
            this.observer.unobserve(this.sentinel.nativeElement);
            requestAnimationFrame(() => this.observer?.observe(this.sentinel!.nativeElement));
        }
    }

    private scrollBehavior(): ScrollBehavior {
        return window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
    }

    private loadFavorites(): void {
        this.http.get<string[]>('/api/v1/reactions/mine', { headers: new HttpHeaders({ 'X-Visitor-Id': this.visitorId }) })
            .pipe(takeUntilDestroyed(this.destroyRef))
            .subscribe({
                next: (ids) => { this.favoriteIds = new Set(ids); this.favoritesLoaded = true; },
                error: () => { this.favoritesLoaded = true; }
            });
    }

    private finishFavorite(productId: string): void {
        const busy = new Set(this.favoriteBusyIds);
        busy.delete(productId);
        this.favoriteBusyIds = busy;
    }

    private getVisitorId(): string {
        const key = 'bazarstore.visitor-id';
        const createId = (): string => typeof crypto !== 'undefined' && 'randomUUID' in crypto
            ? crypto.randomUUID()
            : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (char) => {
                const random = Math.floor(Math.random() * 16);
                return (char === 'x' ? random : (random & 0x3) | 0x8).toString(16);
            });
        try {
            const value = localStorage.getItem(key);
            if (value) return value;
            const id = createId();
            localStorage.setItem(key, id);
            return id;
        } catch {
            return createId();
        }
    }
}
