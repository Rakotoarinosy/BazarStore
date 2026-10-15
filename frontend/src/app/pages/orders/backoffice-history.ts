import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { ButtonModule } from 'primeng/button';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { MessageService } from 'primeng/api';
import { ToastModule } from 'primeng/toast';

interface AuditEntry { id: string; actor_name: string; action: string; entity_type: string; details: string; created_at: string; }
interface PaymentAttempt { id: string; order_reference: string; customer_name: string; customer_email: string; provider: string; status: string; amount: number; provider_reference: string | null; created_at: string; updated_at: string | null; }

@Component({
    selector: 'app-backoffice-history', standalone: true,
    imports: [CommonModule, TableModule, TagModule, ButtonModule, ToastModule],
    providers: [MessageService],
    styleUrl: './backoffice-history.css',
    template: `
        <p-toast />
        <div class="card">
            <div class="flex flex-wrap align-items-center justify-content-between gap-3 mb-4">
                <div><h1 class="text-2xl font-semibold m-0">Journal et paiements</h1><p class="text-color-secondary mb-0 mt-2">Actions enregistrées et historique complet des tentatives de paiement.</p></div>
                <div class="flex gap-2 history-tabs" role="group" aria-label="Historique à afficher">
                    <button type="button" class="history-tab" [class.active]="tab() === 'audit'" [attr.aria-pressed]="tab() === 'audit'" (click)="tab.set('audit')">Journal</button>
                    <button type="button" class="history-tab" [class.active]="tab() === 'payments'" [attr.aria-pressed]="tab() === 'payments'" (click)="tab.set('payments')">Paiements</button>
                </div>
            </div>
            @if (tab() === 'audit') {
                <p-table [value]="audit()" [loading]="loading()" [paginator]="true" [rows]="15" [rowsPerPageOptions]="[15, 30, 50]" [globalFilterFields]="['actor_name','action','details']">
                    <ng-template #header><tr><th>Date</th><th>Utilisateur</th><th>Action</th><th>Détail</th></tr></ng-template>
                    <ng-template #body let-entry><tr><td>{{ formatDate(entry.created_at) }}</td><td>{{ entry.actor_name }}</td><td><p-tag [value]="entry.action" severity="info" /></td><td>{{ entry.details }}</td></tr></ng-template>
                    <ng-template #emptymessage><tr><td colspan="4">Aucune action enregistrée.</td></tr></ng-template>
                </p-table>
            } @else {
                <p-table [value]="payments()" [loading]="loading()" [paginator]="true" [rows]="15" [rowsPerPageOptions]="[15, 30, 50]">
                    <ng-template #header><tr><th>Date</th><th>Client</th><th>Commande</th><th>Moyen</th><th>Montant</th><th>Statut</th><th></th></tr></ng-template>
                    <ng-template #body let-payment><tr><td>{{ formatDate(payment.created_at) }}</td><td><div>{{ payment.customer_name }}</div><small class="text-color-secondary">{{ payment.customer_email }}</small></td><td>{{ payment.order_reference }}</td><td>{{ payment.provider === 'mvola' ? 'MVola' : 'Carte bancaire' }}</td><td>{{ formatPrice(payment.amount) }}</td><td><p-tag [value]="statusLabel(payment.status)" [severity]="severity(payment.status)" /></td><td>@if(payment.status === 'pending') { <button pButton label="Annuler" severity="danger" [text]="true" (click)="cancel(payment)"></button> }</td></tr></ng-template>
                    <ng-template #emptymessage><tr><td colspan="7">Aucune tentative de paiement.</td></tr></ng-template>
                </p-table>
            }
        </div>`
})
export class BackofficeHistory implements OnInit {
    private readonly http = inject(HttpClient);
    private readonly messages = inject(MessageService);
    readonly tab = signal<'audit' | 'payments'>('audit');
    readonly audit = signal<AuditEntry[]>([]);
    readonly payments = signal<PaymentAttempt[]>([]);
    readonly loading = signal(false);

    ngOnInit(): void { this.refresh(); }
    refresh(): void {
        this.loading.set(true);
        this.http.get<AuditEntry[]>('/api/v1/orders/manage/audit').subscribe({ next: (rows) => this.audit.set(rows), error: () => this.messages.add({ severity: 'error', summary: 'Erreur', detail: 'Chargement du journal impossible.' }), complete: () => this.loading.set(false) });
        this.http.get<PaymentAttempt[]>('/api/v1/orders/manage/payments').subscribe({ next: (rows) => this.payments.set(rows), error: () => this.messages.add({ severity: 'error', summary: 'Erreur', detail: 'Chargement des paiements impossible.' }), complete: () => this.loading.set(false) });
    }
    cancel(payment: PaymentAttempt): void {
        this.http.patch<PaymentAttempt>(`/api/v1/orders/manage/payments/${encodeURIComponent(payment.id)}/cancel`, {}).subscribe({
            next: (updated) => { this.payments.update((rows) => rows.map((row) => row.id === updated.id ? updated : row)); this.messages.add({ severity: 'success', summary: 'Paiement annulé', detail: `La tentative ${updated.order_reference} a été annulée.` }); this.http.get<AuditEntry[]>('/api/v1/orders/manage/audit').subscribe((rows) => this.audit.set(rows)); },
            error: () => this.messages.add({ severity: 'error', summary: 'Erreur', detail: 'Annulation impossible.' })
        });
    }
    statusLabel(status: string): string { return ({ pending: 'En cours', completed: 'Terminé', cancelled: 'Annulé', failed: 'Échoué' } as Record<string, string>)[status] ?? status; }
    severity(status: string): 'success' | 'warn' | 'danger' | 'secondary' { return ({ pending: 'warn', completed: 'success', cancelled: 'secondary', failed: 'danger' } as Record<string, 'success' | 'warn' | 'danger' | 'secondary'>)[status] ?? 'secondary'; }
    formatDate(value: string): string { return new Intl.DateTimeFormat('fr-FR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)); }
    formatPrice(value: number): string { return `${new Intl.NumberFormat('fr-FR').format(value)} Ar`; }
}
