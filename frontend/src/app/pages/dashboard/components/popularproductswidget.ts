import { HttpClient } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';

interface PopularProduct {
    product_id: string;
    name: string;
    category: string;
    image_url: string | null;
    visitors_total: number;
    active_favorites: number;
    recent_reactions: number;
}

interface PopularProductsResponse {
    period_days: number;
    products: PopularProduct[];
}

@Component({
    standalone: true,
    selector: 'app-popular-products-widget',
    templateUrl: './popularproductswidget.html'
})
export class PopularProductsWidget {
    private readonly http = inject(HttpClient);
    readonly products = signal<PopularProduct[]>([]);
    readonly periodDays = signal(30);
    readonly loading = signal(true);
    readonly error = signal(false);

    constructor() {
        this.http.get<PopularProductsResponse>('/api/v1/reactions/popular?days=30&limit=5').subscribe({
            next: (result) => {
                this.products.set(result.products);
                this.periodDays.set(result.period_days);
                this.loading.set(false);
            },
            error: () => {
                this.error.set(true);
                this.loading.set(false);
            }
        });
    }
}
