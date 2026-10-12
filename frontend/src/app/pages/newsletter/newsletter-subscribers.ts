import { DatePipe } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ConfirmationService, MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { InputTextModule } from 'primeng/inputtext';
import { TableLazyLoadEvent, TableModule } from 'primeng/table';
import { ToastModule } from 'primeng/toast';
import { ToolbarModule } from 'primeng/toolbar';
import { Subject, debounceTime, distinctUntilChanged } from 'rxjs';

const NEWSLETTER_API = '/api/v1/newsletter/subscriptions';

interface NewsletterSubscriber {
    id: string;
    email: string;
    subscribed_at: string;
}

interface NewsletterSubscribersPage {
    total: number;
    subscribers: NewsletterSubscriber[];
}

@Component({
    selector: 'app-newsletter-subscribers',
    standalone: true,
    imports: [DatePipe, ButtonModule, ConfirmDialogModule, InputTextModule, TableModule, ToastModule, ToolbarModule],
    templateUrl: './newsletter-subscribers.html',
    providers: [ConfirmationService, MessageService]
})
export class NewsletterSubscribers {
    private readonly http = inject(HttpClient);
    private readonly confirmation = inject(ConfirmationService);
    private readonly messages = inject(MessageService);
    private readonly destroyRef = inject(DestroyRef);
    private readonly searchInput = new Subject<string>();

    readonly rows = 20;
    readonly subscribers = signal<NewsletterSubscriber[]>([]);
    readonly total = signal(0);
    readonly loading = signal(true);
    readonly exporting = signal(false);
    readonly search = signal('');
    // Liée au tableau pour que le paginateur revienne en page 1 après une recherche.
    readonly first = signal(0);

    constructor() {
        this.searchInput.pipe(debounceTime(300), distinctUntilChanged(), takeUntilDestroyed(this.destroyRef)).subscribe((search) => {
            this.search.set(search);
            this.first.set(0);
            this.load();
        });
    }

    onLazyLoad(event: TableLazyLoadEvent): void {
        this.first.set(event.first ?? 0);
        this.load();
    }

    onSearch(event: Event): void {
        if (event.target instanceof HTMLInputElement) this.searchInput.next(event.target.value.trim());
    }

    load(): void {
        this.loading.set(true);
        const params: Record<string, string | number> = { limit: this.rows, offset: this.first() };
        if (this.search()) params['search'] = this.search();
        this.http
            .get<NewsletterSubscribersPage>(NEWSLETTER_API, { params })
            .pipe(takeUntilDestroyed(this.destroyRef))
            .subscribe({
                next: (page) => {
                    this.subscribers.set(page.subscribers);
                    this.total.set(page.total);
                    this.loading.set(false);
                },
                error: (error: unknown) => {
                    this.loading.set(false);
                    this.showError(error);
                }
            });
    }

    exportCsv(): void {
        this.exporting.set(true);
        const params: Record<string, string> = this.search() ? { search: this.search() } : {};
        this.http.get(`${NEWSLETTER_API}/export`, { params, observe: 'response', responseType: 'blob' }).subscribe({
            next: (response) => {
                this.exporting.set(false);
                const filename = /filename="([^"]+)"/.exec(response.headers.get('Content-Disposition') ?? '')?.[1] ?? 'newsletter-abonnes.csv';
                const url = URL.createObjectURL(response.body as Blob);
                const link = document.createElement('a');
                link.href = url;
                link.download = filename;
                link.click();
                URL.revokeObjectURL(url);
            },
            error: (error: unknown) => {
                this.exporting.set(false);
                this.showError(error);
            }
        });
    }

    confirmRemove(subscriber: NewsletterSubscriber): void {
        this.confirmation.confirm({
            header: 'Désinscrire cet abonné ?',
            message: `${subscriber.email} ne recevra plus la newsletter. Il pourra se réinscrire depuis la boutique.`,
            icon: 'pi pi-exclamation-triangle',
            acceptLabel: 'Désinscrire',
            rejectLabel: 'Annuler',
            acceptButtonStyleClass: 'p-button-danger',
            accept: () => this.remove(subscriber)
        });
    }

    private remove(subscriber: NewsletterSubscriber): void {
        this.http.delete<void>(`${NEWSLETTER_API}/${encodeURIComponent(subscriber.id)}`).subscribe({
            next: () => {
                this.messages.add({ severity: 'success', summary: 'Abonné désinscrit', detail: subscriber.email, life: 3000 });
                // Revenir à la page précédente si l'on vient de vider la dernière.
                if (this.subscribers().length === 1 && this.first() > 0) this.first.update((first) => first - this.rows);
                this.load();
            },
            error: (error: unknown) => this.showError(error)
        });
    }

    private showError(error: unknown): void {
        const detail = error instanceof HttpErrorResponse && typeof error.error?.detail === 'string'
            ? error.error.detail
            : 'Action impossible pour le moment. Réessayez dans quelques instants.';
        this.messages.add({ severity: 'error', summary: 'Newsletter', detail, life: 5000 });
    }
}
