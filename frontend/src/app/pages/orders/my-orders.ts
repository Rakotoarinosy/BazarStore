import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, inject } from '@angular/core';
import { Router, RouterModule } from '@angular/router';

interface OrderItem {
    id: string;
    product_name: string;
    product_image_url: string | null;
    unit_price: number;
    quantity: number;
    line_total: number;
}

interface CustomerOrder {
    id: string;
    reference: string;
    status: string;
    total_amount: number;
    created_at: string;
    items: OrderItem[];
}

@Component({
    selector: 'app-my-orders',
    standalone: true,
    imports: [RouterModule],
    templateUrl: './my-orders.html'
})
export class MyOrders {
    private readonly http = inject(HttpClient);
    private readonly router = inject(Router);

    orders: CustomerOrder[] = [];
    loading = true;
    errorMessage = '';

    constructor() {
        this.http.get<CustomerOrder[]>('/api/v1/orders/mine').subscribe({
            next: (orders) => {
                this.orders = orders;
                this.loading = false;
            },
            error: (error: unknown) => {
                this.loading = false;
                if (error instanceof HttpErrorResponse && error.status === 401) {
                    void this.router.navigateByUrl('/auth/login');
                    return;
                }
                this.errorMessage = 'Impossible de charger vos commandes. Veuillez réessayer.';
            }
        });
    }

    formatPrice(price: number): string {
        return `${new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 }).format(price)} Ar`;
    }

    formatDate(value: string): string {
        return new Intl.DateTimeFormat('fr-FR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
    }

    statusLabel(status: string): string {
        const labels: Record<string, string> = {
            pending: 'En attente',
            confirmed: 'Confirmée',
            processing: 'En préparation',
            shipped: 'Expédiée',
            completed: 'Terminée',
            cancelled: 'Annulée'
        };
        return labels[status] ?? status;
    }
}
