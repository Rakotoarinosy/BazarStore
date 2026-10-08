import { Component } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';

@Component({
    selector: 'app-register',
    standalone: true,
    imports: [FormsModule, RouterModule],
    templateUrl: './register.html'
})
export class Register {
    firstName = '';
    lastName = '';
    email = '';
    password = '';
    confirmPassword = '';
    acceptTerms = false;
    statusMessage = '';

    submit(event: Event): void {
        event.preventDefault();

        if (this.password !== this.confirmPassword) {
            this.statusMessage = 'Les deux mots de passe ne correspondent pas.';
            return;
        }

        if (!this.acceptTerms) {
            this.statusMessage = 'Veuillez accepter les conditions pour continuer.';
            return;
        }

        this.statusMessage = 'Vos informations sont prêtes. La création de compte sera activée avec le service d’authentification.';
    }
}
