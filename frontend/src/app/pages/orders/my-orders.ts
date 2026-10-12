import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { ConfirmationService } from 'primeng/api';
import { ConfirmPopupModule } from 'primeng/confirmpopup';
import { TimelineModule } from 'primeng/timeline';
import { SseClient } from '../../core/realtime/sse-client';

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
    updated_at: string | null;
    payment_provider: 'stripe' | 'mvola' | null;
    payment_status: 'pending' | 'completed' | 'failed' | null;
    payment_reference: string | null;
    paid_at: string | null;
    invoice_number: string | null;
    items: OrderItem[];
}

interface CardCheckout {
    checkout_url: string;
    order: CustomerOrder;
}

type PaymentMethod = 'stripe' | 'mvola';

interface OrderTimelineStep {
    label: string;
    icon: string;
    state: 'done' | 'current' | 'upcoming' | 'cancelled';
    date: string | null;
}

const ORDER_PROGRESS: { status: string; label: string; icon: string }[] = [
    { status: 'pending', label: 'En attente', icon: 'pi pi-clock' },
    { status: 'confirmed', label: 'Confirmée', icon: 'pi pi-check' },
    { status: 'processing', label: 'En préparation', icon: 'pi pi-box' },
    { status: 'shipped', label: 'Expédiée', icon: 'pi pi-truck' },
    { status: 'completed', label: 'Livrée', icon: 'pi pi-flag' }
];

@Component({
    selector: 'app-my-orders',
    standalone: true,
    imports: [FormsModule, RouterModule, ConfirmPopupModule, TimelineModule],
    templateUrl: './my-orders.html',
    styleUrl: './my-orders.css',
    providers: [ConfirmationService]
})
export class MyOrders {
    private readonly http = inject(HttpClient);
    private readonly router = inject(Router);
    private readonly route = inject(ActivatedRoute);
    private readonly confirmation = inject(ConfirmationService);

    readonly orders = signal<CustomerOrder[]>([]);
    readonly selectedOrder = signal<CustomerOrder | null>(null);
    readonly loading = signal(true);
    readonly errorMessage = signal('');
    readonly paymentMessage = signal('');
    readonly paymentError = signal(false);
    // Moyens activés côté API (PAYMENTS_ENABLED + identifiants du fournisseur).
    readonly cardEnabled = signal(false);
    readonly mvolaEnabled = signal(false);
    readonly selectedPaymentMethod = signal<PaymentMethod | null>(null);
    readonly showPaymentMethods = signal(false);
    readonly mvolaPhone = signal('');
    readonly paymentBusy = signal(false);
    readonly cancelBusy = signal(false);
    readonly invoiceDownloading = signal<string | null>(null);
    readonly invoiceError = signal('');

    constructor() {
        // Temps réel : statut changé par l'équipe, paiement confirmé, facture émise…
        inject(SseClient)
            .stream('/api/v1/orders/mine/stream')
            .pipe(takeUntilDestroyed())
            .subscribe((message) => {
                if (message.event === 'order') this.applyOrder(JSON.parse(message.data) as CustomerOrder);
            });

        this.http.get<CustomerOrder[]>('/api/v1/orders/mine').subscribe({
            next: (orders) => {
                this.orders.set(orders);
                this.loading.set(false);
                this.loadPaymentConfig();
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
            completed: 'Livrée',
            cancelled: 'Annulée'
        };
        return labels[status] ?? status;
    }

    timelineSteps(order: CustomerOrder): OrderTimelineStep[] {
        if (order.status === 'cancelled') {
            return [
                { label: 'Commande passée', icon: 'pi pi-shopping-cart', state: 'done', date: order.created_at },
                { label: 'Annulée', icon: 'pi pi-times', state: 'cancelled', date: order.updated_at }
            ];
        }

        const currentIndex = ORDER_PROGRESS.findIndex((step) => step.status === order.status);
        return ORDER_PROGRESS.map((step, index) => ({
            label: step.label,
            icon: step.icon,
            state: index < currentIndex ? 'done' : index === currentIndex ? 'current' : 'upcoming',
            date: index === 0 ? order.created_at : index === currentIndex ? order.updated_at : null
        }));
    }

    isCardPending(order: CustomerOrder): boolean {
        return order.status === 'pending' && order.payment_provider === 'stripe' && order.payment_status === 'pending';
    }

    isMvolaPending(order: CustomerOrder): boolean {
        return order.status === 'pending' && order.payment_provider === 'mvola' && order.payment_status === 'pending';
    }

    canCancel(order: CustomerOrder): boolean {
        return order.status === 'pending' && order.payment_status !== 'pending' && order.payment_status !== 'completed';
    }

    cancelOrder(order: CustomerOrder, event: Event): void {
        if (!this.canCancel(order) || this.cancelBusy()) return;

        this.confirmation.confirm({
            key: 'cancel-order',
            target: event.currentTarget as HTMLElement,
            message: `Voulez-vous vraiment annuler la commande « ${order.reference} » ?`,
            icon: 'pi pi-exclamation-triangle',
            rejectLabel: 'Garder ma commande',
            acceptLabel: 'Oui, annuler',
            rejectButtonStyleClass: 'p-button-secondary p-button-outlined',
            acceptButtonStyleClass: 'p-button-danger',
            accept: () => this.submitCancelOrder(order)
        });
    }

    private submitCancelOrder(order: CustomerOrder): void {
        if (!this.canCancel(order) || this.cancelBusy()) return;
        this.cancelBusy.set(true);
        this.setPaymentMessage('Annulation de la commande…');
        this.http.post<CustomerOrder>(`/api/v1/orders/${order.id}/cancel`, {}).subscribe({
            next: (updated) => {
                this.cancelBusy.set(false);
                this.applyOrder(updated);
                this.setPaymentMessage('La commande a été annulée.', false);
            },
            error: (error: unknown) => {
                this.cancelBusy.set(false);
                const detail = error instanceof HttpErrorResponse && typeof error.error?.detail === 'string'
                    ? error.error.detail
                    : 'La commande n’a pas pu être annulée. Veuillez réessayer.';
                this.setPaymentMessage(detail, true);
            }
        });
    }

    openDetails(order: CustomerOrder): void {
        this.setPaymentMessage('');
        this.invoiceError.set('');
        this.selectedOrder.set(order);
        this.showPaymentMethods.set(false);
        this.mvolaPhone.set('');
        this.setDefaultPaymentMethod();
    }

    selectPaymentMethod(method: PaymentMethod): void {
        this.selectedPaymentMethod.set(method);
    }

    beginPaymentSelection(): void {
        this.setDefaultPaymentMethod();
        this.showPaymentMethods.set(true);
    }

    backToPaymentSummary(): void {
        this.showPaymentMethods.set(false);
        this.mvolaPhone.set('');
    }

    confirmPayment(): void {
        if (this.selectedPaymentMethod() === 'stripe') this.startCardPayment();
        else if (this.selectedPaymentMethod() === 'mvola') this.startMvolaPayment();
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
        this.http.post<CardCheckout>(`/api/v1/orders/${order.id}/payments/stripe`, {}).subscribe({
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

    startMvolaPayment(): void {
        const order = this.selectedOrder();
        const phone = this.mvolaPhone().trim();
        if (!order || order.status !== 'pending' || !phone || this.paymentBusy()) return;

        this.paymentBusy.set(true);
        this.setPaymentMessage('Envoi de la demande de paiement MVola…');
        this.http.post<CustomerOrder>(`/api/v1/orders/${order.id}/payments/mvola`, { phone }).subscribe({
            next: (updated) => {
                this.paymentBusy.set(false);
                this.applyOrder(updated);
                this.setPaymentMessage('Demande envoyée. Validez le paiement sur votre téléphone MVola.');
            },
            error: (error: unknown) => {
                this.paymentBusy.set(false);
                this.setPaymentMessage(this.paymentErrorMessage(error), true);
            }
        });
    }

    checkMvolaPayment(): void {
        const order = this.selectedOrder();
        if (order && this.isMvolaPending(order)) this.refreshMvolaPayment(order.id, true);
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
        this.http.get<CustomerOrder>(`/api/v1/orders/${orderId}/payments/stripe`).subscribe({
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

    private refreshMvolaPayment(orderId: string, showResult = false): void {
        this.paymentBusy.set(true);
        this.http.get<CustomerOrder>(`/api/v1/orders/${orderId}/payments/mvola`).subscribe({
            next: (updated) => {
                this.paymentBusy.set(false);
                this.applyOrder(updated);
                if (!showResult) return;
                if (updated.payment_status === 'completed') this.setPaymentMessage('Paiement MVola reçu, merci ! Votre commande est confirmée.');
                else if (updated.payment_status === 'failed') this.setPaymentMessage('Le paiement MVola a échoué. Vous pouvez réessayer.', true);
                else this.setPaymentMessage('Paiement en attente. Validez la demande sur votre téléphone puis vérifiez à nouveau.');
            },
            error: (error: unknown) => {
                this.paymentBusy.set(false);
                if (showResult) this.setPaymentMessage(this.paymentErrorMessage(error), true);
            }
        });
    }

    private loadPaymentConfig(): void {
        this.http.get<{ card_enabled: boolean; mvola_enabled: boolean }>('/api/v1/orders/payments/config').subscribe({
            next: (config) => {
                this.cardEnabled.set(config.card_enabled);
                this.mvolaEnabled.set(config.mvola_enabled);
                this.setDefaultPaymentMethod();
                if (config.card_enabled) this.handleStripeReturn();
                // Paiements lancés mais pas encore confirmés (client revenu sans passer par Stripe).
                for (const order of this.orders()) {
                    if (config.card_enabled && this.isCardPending(order)) this.refreshCardPayment(order.id);
                    else if (config.mvola_enabled && this.isMvolaPending(order)) this.refreshMvolaPayment(order.id);
                }
            },
            error: () => {
                this.cardEnabled.set(false);
                this.mvolaEnabled.set(false);
                this.selectedPaymentMethod.set(null);
            }
        });
    }

    private setDefaultPaymentMethod(): void {
        if (this.cardEnabled()) this.selectedPaymentMethod.set('stripe');
        else if (this.mvolaEnabled()) this.selectedPaymentMethod.set('mvola');
        else this.selectedPaymentMethod.set(null);
    }

    /** Retour de Stripe : /my-orders?order=<id>&payment=success|cancelled */
    private handleStripeReturn(): void {
        const params = this.route.snapshot.queryParamMap;
        const order = this.orders().find((candidate) => candidate.id === params.get('order'));
        const result = params.get('payment');
        if (!order || !result) return;

        this.openDetails(order);
        if (result === 'success') {
            this.setPaymentMessage('Paiement en cours de vérification…');
            this.refreshCardPayment(order.id, true);
        } else {
            this.setPaymentMessage('Paiement annulé. Vous pouvez réessayer quand vous voulez.', true);
        }
        // Nettoie l'URL pour qu'un rechargement ne rejoue pas le message.
        void this.router.navigate([], { queryParams: {}, replaceUrl: true });
    }

    private applyOrder(updated: CustomerOrder): void {
        this.orders.update((orders) =>
            orders.some((order) => order.id === updated.id) ? orders.map((order) => (order.id === updated.id ? updated : order)) : [updated, ...orders]
        );
        if (this.selectedOrder()?.id === updated.id) this.selectedOrder.set(updated);
        if (updated.payment_provider === 'mvola' && updated.payment_status === 'completed') {
            this.setPaymentMessage('Paiement MVola reçu, merci ! Votre commande est confirmée.');
        } else if (updated.payment_provider === 'mvola' && updated.payment_status === 'failed') {
            this.setPaymentMessage('Le paiement MVola a échoué. Vous pouvez réessayer.', true);
        }
    }

    private setPaymentMessage(message: string, isError = false): void {
        this.paymentMessage.set(message);
        this.paymentError.set(isError);
    }

    private paymentErrorMessage(error: unknown): string {
        if (error instanceof HttpErrorResponse) {
            if (error.status === 503) return error.error?.detail ?? 'Le paiement en ligne est indisponible pour le moment.';
            if (error.status === 409) return error.error?.detail ?? 'Cette commande ne peut plus être payée.';
            if (error.status === 401) return 'Votre session a expiré. Reconnectez-vous.';
            if (error.status === 400 || error.status === 422) {
                const detail = error.error?.detail;
                if (typeof detail === 'string') return detail;
                if (Array.isArray(detail) && typeof detail[0]?.msg === 'string') return detail[0].msg;
            }
        }
        return 'Le paiement n’a pas pu être lancé. Veuillez réessayer.';
    }
}
