import { Component, inject, signal } from '@angular/core';
import { RippleModule } from 'primeng/ripple';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { CommonModule } from '@angular/common';
import { Product, ProductService } from '@/app/pages/service/product.service';

@Component({
    standalone: true,
    selector: 'app-recent-sales-widget',
    imports: [CommonModule, TableModule, ButtonModule, RippleModule],
    templateUrl: './recentsaleswidget.html',
    providers: [ProductService]
})
export class RecentSalesWidget {
    products = signal<Product[]>([]);

    productService = inject(ProductService);

    ngOnInit() {
        this.productService.getProductsSmall().then((data) => (this.products.set(data)));
    }
}
