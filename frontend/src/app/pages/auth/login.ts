import { AfterViewInit, Component, ElementRef, ViewChild, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterModule } from '@angular/router';
import { AuthService, authErrorMessage, googleAuthErrorMessage } from '../../core/auth/auth.service';
import { GoogleIdentityService } from '../../core/auth/google-identity.service';

@Component({
    selector: 'app-login',
    standalone: true,
    imports: [FormsModule, RouterModule],
    templateUrl: './login.html'
})
export class Login implements AfterViewInit {
    private readonly auth = inject(AuthService);
    private readonly router = inject(Router);
    private readonly googleIdentity = inject(GoogleIdentityService);

    @ViewChild('googleButton', { static: true }) private googleButton!: ElementRef<HTMLDivElement>;

    email = '';
    password = '';
    rememberMe = false;
    readonly statusMessage = signal('');
    readonly googleWidgetReady = signal(false);

    ngAfterViewInit(): void {
        this.googleIdentity.renderButton(
            this.googleButton.nativeElement,
            (credential) => {
                this.statusMessage.set('');
                this.auth.loginWithGoogle(credential).subscribe({
                    next: (session) => this.navigateForRole(session.user.role),
                    error: (error: unknown) => this.statusMessage.set(googleAuthErrorMessage(error))
                });
            },
            (message) => this.statusMessage.set(message),
            () => this.googleWidgetReady.set(true)
        );
    }

    submit(event: Event): void {
        event.preventDefault();
        this.statusMessage.set('');
        this.auth.login(this.email, this.password).subscribe({
            next: (session) => this.navigateForRole(session.user.role),
            error: (error: unknown) => this.statusMessage.set(authErrorMessage(error))
        });
    }

    requestPasswordReset(): void {
        this.statusMessage.set('La récupération du mot de passe n’est pas encore disponible.');
    }

    showGoogleConfigurationMessage(): void {
        this.statusMessage.set('La connexion Google n’est pas configurée ou est temporairement indisponible.');
    }

    private navigateForRole(role: string): void {
        const backofficeRoles = ['admin', 'commercial', 'manager'];
        void this.router.navigateByUrl(backofficeRoles.includes(role) ? '/backoffice' : '/');
    }

}
