import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, ViewChild, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ConfirmationService, MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { Table, TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { ToastModule } from 'primeng/toast';
import { ToolbarModule } from 'primeng/toolbar';
import { ManagedOrder, ORDER_TRANSITIONS, OrderAdminStore, OrderStatus } from '../../core/orders/order-admin.store';

type Severity = 'success' | 'info' | 'warn' | 'danger' | 'secondary' | 'contrast';

const STATUS_LABELS: Record<OrderStatus, string> = {
    pending: 'En attente',
    confirmed: 'Confirmée',
    processing: 'En préparation',
    shipped: 'Expédiée',
    completed: 'Livrée',
    cancelled: 'Annulée'
};

const STATUS_SEVERITY: Record<OrderStatus, Severity> = {
    pending: 'warn',
    confirmed: 'info',
    processing: 'contrast',
    shipped: 'secondary',
    completed: 'success',
    cancelled: 'danger'
};

/** Libellé et style du bouton qui fait passer la commande à ce statut. */
const ACTIONS: Record<OrderStatus, { label: string; icon: string; severity?: Severity }> = {
    pending: { label: 'Remettre en attente', icon: 'pi pi-clock' },
    confirmed: { label: 'Confirmer', icon: 'pi pi-check' },
    processing: { label: 'Passer en préparation', icon: 'pi pi-box' },
    shipped: { label: 'Marquer expédiée', icon: 'pi pi-truck' },
    completed: { label: 'Marquer livrée', icon: 'pi pi-flag' },
    cancelled: { label: 'Annuler la commande', icon: 'pi pi-times', severity: 'danger' }
};

@Component({
    selector: 'app-order-management',
    standalone: true,
    imports: [CommonModule, FormsModule, TableModule, ToolbarModule, ButtonModule, DialogModule, InputTextModule, SelectModule, TagModule, ToastModule, ConfirmDialogModule],
    templateUrl: './order-management.html',
    styleUrl: './order-management.css',
    providers: [ConfirmationService, MessageService]
})
export class OrderManagement implements OnInit {
    private readonly ordersApi = inject(OrderAdminStore);
    private readonly confirmation = inject(ConfirmationService);
    private readonly messages = inject(MessageService);

    @ViewChild('ordersTable') ordersTable?: Table;

    readonly orders = this.ordersApi.orders;
    readonly loading = this.ordersApi.loading;
    readonly statusFilter = signal<OrderStatus | null>(null);
    readonly selected = signal<ManagedOrder | null>(null);
    readonly updating = signal(false);
    readonly downloading = signal(false);
    dialogVisible = false;

    readonly statusOptions = (Object.keys(STATUS_LABELS) as OrderStatus[]).map((value) => ({ value, label: STATUS_LABELS[value] }));

    readonly filteredOrders = computed(() => {
        const status = this.statusFilter();
        return status ? this.orders().filter((order) => order.status === status) : this.orders();
    });
    readonly toProcessCount = computed(() => this.orders().filter((order) => order.status === 'pending' || order.status === 'confirmed').length);
    readonly inProgressCount = computed(() => this.orders().filter((order) => order.status === 'processing' || order.status === 'shipped').length);
    readonly collectedRevenue = computed(() =>
        this.orders()
            .filter((order) => order.payment_status === 'completed' && order.status !== 'cancelled')
            .reduce((total, order) => total + order.total_amount, 0)
    );

    ngOnInit(): void {
        this.refresh();
    }

    refresh(): void {
        this.ordersApi.list().subscribe({ error: (error: unknown) => this.showError(error) });
    }

    onSearch(event: Event): void {
        this.ordersTable?.filterGlobal((event.target as HTMLInputElement).value, 'contains');
    }

    openOrder(order: ManagedOrder): void {
        this.selected.set(order);
        this.dialogVisible = true;
    }

    nextStatuses(order: ManagedOrder): OrderStatus[] {
        return ORDER_TRANSITIONS[order.status];
    }

    action(status: OrderStatus) {
        return ACTIONS[status];
    }

    statusLabel(status: OrderStatus): string {
        return STATUS_LABELS[status];
    }

    statusSeverity(status: OrderStatus): Severity {
        return STATUS_SEVERITY[status];
    }

    paymentLabel(order: ManagedOrder): string {
        if (order.payment_status === 'completed') return order.payment_provider === 'mvola' ? 'Payée · MVola' : 'Payée · carte';
        if (order.payment_status === 'pending') return 'Paiement en cours';
        if (order.payment_status === 'failed') return 'Paiement échoué';
        return 'Non payée';
    }

    paymentSeverity(order: ManagedOrder): Severity {
        if (order.payment_status === 'completed') return 'success';
        if (order.payment_status === 'failed') return 'danger';
        return order.payment_status === 'pending' ? 'warn' : 'secondary';
    }

    itemCount(order: ManagedOrder): number {
        return order.items.reduce((total, item) => total + item.quantity, 0);
    }

    formatPrice(price: number): string {
        return `${new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 }).format(price)} Ar`;
    }

    formatDate(value: string | null): string {
        return value ? new Intl.DateTimeFormat('fr-FR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '—';
    }

    changeStatus(order: ManagedOrder, status: OrderStatus): void {
        if (status !== 'cancelled') {
            this.applyStatus(order, status);
            return;
        }
        const paid = order.payment_status === 'completed';
        this.confirmation.confirm({
            header: 'Annuler la commande',
            message: paid
                ? `La commande ${order.reference} a déjà été payée. Après l’annulation, pensez à rembourser le client depuis le dashboard Stripe. Continuer ?`
                : `Annuler la commande ${order.reference} ? Le stock réservé sera restitué.`,
            icon: 'pi pi-exclamation-triangle',
            acceptLabel: 'Annuler la commande',
            rejectLabel: 'Retour',
            acceptButtonStyleClass: 'p-button-danger',
            accept: () => this.applyStatus(order, status)
        });
    }

    downloadInvoice(order: ManagedOrder): void {
        this.downloading.set(true);
        this.ordersApi.downloadInvoice(order.id).subscribe({
            next: (response) => {
                this.downloading.set(false);
                const filename = /filename="([^"]+)"/.exec(response.headers.get('Content-Disposition') ?? '')?.[1] ?? `facture-${order.reference}.pdf`;
                const url = URL.createObjectURL(response.body as Blob);
                const link = document.createElement('a');
                link.href = url;
                link.download = filename;
                link.click();
                URL.revokeObjectURL(url);
                // Le numéro est attribué au premier téléchargement : on recharge pour l'afficher.
                if (!order.invoice_number) this.refreshSelected(order.id);
            },
            error: (error: unknown) => {
                this.downloading.set(false);
                this.showError(error);
            }
        });
    }

    private applyStatus(order: ManagedOrder, status: OrderStatus): void {
        this.updating.set(true);
        this.ordersApi.updateStatus(order.id, status).subscribe({
            next: (updated) => {
                this.updating.set(false);
                if (this.selected()?.id === updated.id) this.selected.set(updated);
                this.messages.add({ severity: 'success', summary: 'Commande mise à jour', detail: `${updated.reference} · ${STATUS_LABELS[updated.status]}`, life: 3500 });
            },
            error: (error: unknown) => {
                this.updating.set(false);
                this.showError(error);
            }
        });
    }

    private refreshSelected(orderId: string): void {
        this.ordersApi.list().subscribe((orders) => {
            const updated = orders.find((order) => order.id === orderId);
            if (updated && this.selected()?.id === orderId) this.selected.set(updated);
        });
    }

    private showError(error: unknown): void {
        let detail = 'Une erreur est survenue. Réessayez.';
        if (error instanceof HttpErrorResponse) {
            if (error.status === 401 || error.status === 403) detail = 'La gestion des commandes est réservée à l’équipe BazarStore.';
            else if (error.status === 404) detail = 'Cette commande n’existe plus. Rechargez la liste.';
            else if (error.status === 409) detail = error.error?.detail ?? 'Cette action n’est pas possible pour cette commande.';
            else if (error.status === 0) detail = 'Le serveur BazarStore est injoignable.';
        }
        this.messages.add({ severity: 'error', summary: 'Opération impossible', detail, life: 5000 });
    }
}
