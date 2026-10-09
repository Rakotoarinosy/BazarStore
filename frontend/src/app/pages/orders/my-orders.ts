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
    payment_provider: 'card' | 'mvola' | null;
    payment_status: 'pending' | 'completed' | 'failed' | null;
    payment_reference: string | null;
    paid_at: string | null;
    invoice_number: string | null;
    items: OrderItem[];
}

// Paiement en ligne désactivé pour l'instant (à réactiver avec PAYMENTS_ENABLED=true côté API).
const PAYMENTS_ENABLED = false;

interface CardCheckout {
    checkout_url: string;
    order: CustomerOrder;
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
    readonly paymentError = signal(false);
    readonly paymentsEnabled = PAYMENTS_ENABLED;
    readonly paymentBusy = signal(false);
    readonly invoiceDownloading = signal<string | null>(null);
    readonly invoiceError = signal('');

    constructor() {
        this.http.get<CustomerOrder[]>('/api/v1/orders/mine').subscribe({
            next: (orders) => {
                this.orders.set(orders);
                this.loading.set(false);
                // Retour de Stripe : on vérifie les paiements par carte encore en attente.
                if (!PAYMENTS_ENABLED) return;
                for (const order of orders) {
                    if (this.isCardPending(order)) this.refreshCardPayment(order.id);
                }
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

    isCardPending(order: CustomerOrder): boolean {
        return order.status === 'pending' && order.payment_provider === 'card' && order.payment_status === 'pending';
    }

    openDetails(order: CustomerOrder): void {
        this.setPaymentMessage('');
        this.invoiceError.set('');
        this.selectedOrder.set(order);
    }

    closeDetails(): void {
        this.selectedOrder.set(null);
        this.setPaymentMessage('');
    }

    startCardPayment(): void {
        const order = this.selectedOrder();
        if (!order || this.paymentBusy()) return;

        this.paymentBusy.set(true);
        this.setPaymentMessage('Redirection vers la page de paiement sécurisée Stripe…');
        this.http.post<CardCheckout>(`/api/v1/orders/${order.id}/payments/card`, {}).subscribe({
            next: (checkout) => {
                this.applyOrder(checkout.order);
                window.location.assign(checkout.checkout_url);
            },
            error: (error: unknown) => {
                this.paymentBusy.set(false);
                this.setPaymentMessage(this.paymentErrorMessage(error), true);
            }
        });
    }

    checkCardPayment(): void {
        const order = this.selectedOrder();
        if (order) this.refreshCardPayment(order.id, true);
    }

    downloadInvoice(order: CustomerOrder): void {
        if (this.invoiceDownloading()) return;
        this.invoiceDownloading.set(order.id);
        this.invoiceError.set('');
        // Requête authentifiée (Bearer) : un simple lien <a href> n'enverrait pas le jeton.
        this.http.get(`/api/v1/orders/${order.id}/invoice`, { observe: 'response', responseType: 'blob' }).subscribe({
            next: (response) => {
                this.invoiceDownloading.set(null);
                const filename = /filename="([^"]+)"/.exec(response.headers.get('Content-Disposition') ?? '')?.[1] ?? `facture-${order.reference}.pdf`;
                const url = URL.createObjectURL(response.body as Blob);
                const link = document.createElement('a');
                link.href = url;
                link.download = filename;
                link.click();
                URL.revokeObjectURL(url);
                // Le numéro de facture est attribué au premier téléchargement.
                const invoiceNumber = filename.replace(/^facture-|\.pdf$/g, '');
                this.applyOrder({ ...order, invoice_number: invoiceNumber });
            },
            error: () => {
                this.invoiceDownloading.set(null);
                this.invoiceError.set('La facture n’a pas pu être générée. Veuillez réessayer.');
            }
        });
    }

    private refreshCardPayment(orderId: string, showResult = false): void {
        this.paymentBusy.set(true);
        this.http.get<CustomerOrder>(`/api/v1/orders/${orderId}/payments/card`).subscribe({
            next: (updated) => {
                this.paymentBusy.set(false);
                this.applyOrder(updated);
                if (!showResult) return;
                if (updated.payment_status === 'completed') this.setPaymentMessage('Paiement reçu, merci ! Votre commande est confirmée.');
                else this.setPaymentMessage('Paiement pas encore reçu. Si vous venez de payer, réessayez dans quelques instants.', true);
            },
            error: (error: unknown) => {
                this.paymentBusy.set(false);
                if (showResult) this.setPaymentMessage(this.paymentErrorMessage(error), true);
            }
        });
    }

    private applyOrder(updated: CustomerOrder): void {
        this.orders.update((orders) => orders.map((order) => (order.id === updated.id ? updated : order)));
        if (this.selectedOrder()?.id === updated.id) this.selectedOrder.set(updated);
    }

    private setPaymentMessage(message: string, isError = false): void {
        this.paymentMessage.set(message);
        this.paymentError.set(isError);
    }

    private paymentErrorMessage(error: unknown): string {
        if (error instanceof HttpErrorResponse) {
            if (error.status === 503) return error.error?.detail ?? 'Le paiement par carte est indisponible pour le moment.';
            if (error.status === 409) return error.error?.detail ?? 'Cette commande ne peut plus être payée.';
            if (error.status === 401) return 'Votre session a expiré. Reconnectez-vous.';
        }
        return 'Le paiement n’a pas pu être lancé. Veuillez réessayer.';
    }
}
