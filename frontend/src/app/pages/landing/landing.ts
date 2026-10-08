import { CurrencyPipe } from '@angular/common';
import { Component, inject } from '@angular/core';
import { RouterModule } from '@angular/router';
import { Product, ProductService } from '../service/product.service';

@Component({
    selector: 'app-landing',
    standalone: true,
    imports: [CurrencyPipe, RouterModule],
    providers: [ProductService],
    templateUrl: './landing.html'
})
export class Landing {
    private readonly productService = inject(ProductService);

    readonly products = this.productService.getProductsData();
    searchTerm = '';
    selectedCategory = '';
    cartItems: Product[] = [];
    favoriteIds = new Set<string>();
    cartOpen = false;
    newsletterEmail = '';
    subscriptionMessage = '';

    get filteredProducts() {
        const search = this.searchTerm.trim().toLocaleLowerCase();

        return this.products.filter((product) => {
            const matchesCategory = !this.selectedCategory || product.category === this.selectedCategory;
            const matchesSearch =
                !search || `${product.name ?? ''} ${product.category ?? ''} ${product.description ?? ''}`.toLocaleLowerCase().includes(search);

            return matchesCategory && matchesSearch;
        }).slice(0, 8);
    }

    get cartTotal(): number {
        return this.cartItems.reduce((total, product) => total + (product.price ?? 0), 0);
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

    categoryLabel(category: string | undefined): string {
        switch (category) {
            case 'Clothing':
                return 'Mode';
            case 'Electronics':
                return 'High-tech';
            case 'Fitness':
                return 'Sport & bien-être';
            case 'Accessories':
                return 'Accessoires';
            default:
                return 'À découvrir';
        }
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

    addToCart(product: Product): void {
        this.cartItems = [...this.cartItems, product];
        this.cartOpen = true;
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
