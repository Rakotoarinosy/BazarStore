import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterModule } from '@angular/router';

type UnsubscribeState = 'confirm' | 'sending' | 'done' | 'invalid' | 'error';

/**
 * Page ouverte depuis le lien de désinscription d'un e-mail. La désinscription
 * demande un clic : un GET seul serait déclenché par les antivirus de messagerie.
 */
@Component({
    selector: 'app-newsletter-unsubscribe',
    standalone: true,
    imports: [RouterModule],
    templateUrl: './newsletter-unsubscribe.html',
    styleUrl: './newsletter-unsubscribe.scss'
})
export class NewsletterUnsubscribe {
    private readonly http = inject(HttpClient);
    private readonly destroyRef = inject(DestroyRef);
    private readonly token = inject(ActivatedRoute).snapshot.queryParamMap.get('token') ?? '';

    readonly state = signal<UnsubscribeState>(this.token ? 'confirm' : 'invalid');

    unsubscribe(): void {
        if (this.state() === 'sending') return;
        this.state.set('sending');
        this.http
            .post('/api/v1/newsletter/unsubscribe', { token: this.token })
            .pipe(takeUntilDestroyed(this.destroyRef))
            .subscribe({
                next: () => this.state.set('done'),
                error: (error: HttpErrorResponse) => this.state.set(error.status === 404 || error.status === 422 ? 'invalid' : 'error')
            });
    }
}
