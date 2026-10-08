import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterModule } from '@angular/router';
import { switchMap } from 'rxjs';
import { AuthService, authErrorMessage } from '../../core/auth/auth.service';

@Component({
    selector: 'app-register',
    standalone: true,
    imports: [FormsModule, RouterModule],
    templateUrl: './register.html'
})
export class Register {
    private readonly auth = inject(AuthService);
    private readonly router = inject(Router);

    firstName = '';
    lastName = '';
    email = '';
    password = '';
    confirmPassword = '';
    acceptTerms = false;
    readonly statusMessage = signal('');
    readonly isSubmitting = signal(false);

    submit(event: Event): void {
        event.preventDefault();

        if (this.password !== this.confirmPassword) {
            this.statusMessage.set('Les deux mots de passe ne correspondent pas.');
            return;
        }

        if (!this.acceptTerms) {
            this.statusMessage.set('Veuillez accepter les conditions pour continuer.');
            return;
        }

        this.statusMessage.set('');
        this.isSubmitting.set(true);
        const name = `${this.firstName.trim()} ${this.lastName.trim()}`.trim();

        this.auth
            .register(name, this.email, this.password)
            .pipe(switchMap(() => this.auth.login(this.email, this.password)))
            .subscribe({
                next: () => void this.router.navigateByUrl('/'),
                error: (error: unknown) => {
                    this.statusMessage.set(authErrorMessage(error));
                    this.isSubmitting.set(false);
                }
            });
    }
}
