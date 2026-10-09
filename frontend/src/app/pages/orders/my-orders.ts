import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
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
    templateUrl: './my-orders.html',
    styleUrl: './my-orders.css'
})
export class MyOrders {
    private readonly http = inject(HttpClient);
    private readonly router = inject(Router);

    readonly orders = signal<CustomerOrder[]>([]);
    readonly selectedOrder = signal<CustomerOrder | null>(null);
    readonly loading = signal(true);
    readonly errorMessage = signal('');
    readonly paymentMessage = signal('');

    constructor() {
        this.http.get<CustomerOrder[]>('/api/v1/orders/mine').subscribe({
            next: (orders) => {
                this.orders.set(orders);
                this.loading.set(false);
            },
            error: (error: unknown) => {
                this.loading.set(false);
                if (error instanceof HttpErrorResponse && error.status === 401) {
                    void this.router.navigateByUrl('/auth/login');
                    return;
                }
                this.errorMessage.set('Impossible de charger vos commandes. Veuillez réessayer.');
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

    openDetails(order: CustomerOrder): void {
        this.paymentMessage.set('');
        this.selectedOrder.set(order);
    }

    startPayment(): void {
        this.paymentMessage.set(
            'Le paiement Mobile Money n’est pas encore configuré. Aucun paiement n’a été lancé. Les accès marchands MVola, Orange Money ou Airtel Money sont nécessaires pour payer cette commande.'
        );
    }

    closeDetails(): void {
        this.selectedOrder.set(null);
        this.paymentMessage.set('');
    }
}
