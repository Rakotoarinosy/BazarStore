import { Component } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';

@Component({
    selector: 'app-login',
    standalone: true,
    imports: [FormsModule, RouterModule],
    templateUrl: './login.html'
})
export class Login {
    email = '';
    password = '';
    rememberMe = false;
    statusMessage = '';

    submit(event: Event): void {
        event.preventDefault();
        this.statusMessage = 'La connexion sera disponible dès que le service d’authentification sera activé.';
    }

    requestPasswordReset(): void {
        this.statusMessage = 'La récupération du mot de passe sera disponible avec le service d’authentification.';
    }

    startGoogleAuth(): void {
        this.statusMessage = 'La connexion avec Google sera disponible dès que le service d’authentification sera configuré.';
    }
}
