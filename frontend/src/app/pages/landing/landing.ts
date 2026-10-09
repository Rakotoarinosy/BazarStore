import { Component, inject } from '@angular/core';
import { Router, RouterModule } from '@angular/router';
import { EMPTY, catchError, finalize } from 'rxjs';
import { AuthService } from '../../core/auth/auth.service';
import { CatalogProduct, ProductCatalogStore } from '../../core/products/product-catalog.store';

@Component({
    selector: 'app-landing',
    standalone: true,
    imports: [RouterModule],
    templateUrl: './landing.html'
})
export class Landing {
    private readonly router = inject(Router);
    readonly catalog = inject(ProductCatalogStore);
    readonly auth = inject(AuthService);

    readonly currentYear = new Date().getFullYear();
    searchTerm = '';
    selectedCategory = '';
    cartItems: { product: CatalogProduct; quantity: number }[] = [];
    favoriteIds = new Set<string>();
    cartOpen = false;
    newsletterEmail = '';
    subscriptionMessage = '';
    loggingOut = false;

    constructor() {
        this.catalog.load(true).subscribe();
        // Restaure la session depuis le cookie HttpOnly après un rechargement.
        this.auth
            .refresh()
            .pipe(
                catchError(() => {
                    this.auth.clearSession();
                    return EMPTY;
                })
            )
            .subscribe();
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
        return this.catalog.categories().filter((category) => this.catalog.products().some((product) => product.category_id === category.id));
    }

    get showBackofficeLink(): boolean {
        return ['admin', 'commercial', 'manager'].includes(this.auth.currentUser()?.role ?? '');
    }

    get cartTotal(): number {
        return this.cartItems.reduce((total, item) => total + (item.product.price ?? 0) * item.quantity, 0);
    }

    get cartItemCount(): number {
        return this.cartItems.reduce((total, item) => total + item.quantity, 0);
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
        this.cartOpen = true;
    }

    changeQuantity(index: number, change: number): void {
        const item = this.cartItems[index];
        if (!item) return;

        const quantity = item.quantity + change;
        this.cartItems = quantity > 0
            ? this.cartItems.map((entry, itemIndex) => itemIndex === index ? { ...entry, quantity } : entry)
            : this.cartItems.filter((_, itemIndex) => itemIndex !== index);
    }

    removeFromCart(index: number): void {
        this.cartItems = this.cartItems.filter((_, itemIndex) => itemIndex !== index);
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
