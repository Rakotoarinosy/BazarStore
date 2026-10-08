import { CommonModule } from '@angular/common';
import { Component, OnInit, ViewChild, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { ConfirmationService, MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { Table, TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { ToastModule } from 'primeng/toast';
import { ToolbarModule } from 'primeng/toolbar';
import { ManagedUser, UpdateManagedUser, UserAdminStore } from '../../core/users/user-admin.store';
import { AuthService } from '../../core/auth/auth.service';

type UserRole = 'customer' | 'commercial' | 'admin' | 'manager' | 'agent' | 'citizen';

interface UserForm {
    name: string;
    email: string;
    role: UserRole;
    is_active: boolean;
    password: string;
}

@Component({
    selector: 'app-users',
    standalone: true,
    imports: [CommonModule, FormsModule, TableModule, ToolbarModule, ButtonModule, DialogModule, InputTextModule, TagModule, ToastModule, ConfirmDialogModule],
    templateUrl: './users.html',
    styleUrl: './users.css',
    providers: [ConfirmationService, MessageService]
})
export class Users implements OnInit {
    private readonly usersApi = inject(UserAdminStore);
    private readonly auth = inject(AuthService);
    private readonly confirmation = inject(ConfirmationService);
    private readonly messages = inject(MessageService);

    @ViewChild('usersTable') usersTable?: Table;

    readonly users = this.usersApi.users;
    readonly loading = signal(false);
    readonly saving = signal(false);
    dialogVisible = false;
    submitted = false;
    editingUser: ManagedUser | null = null;
    form: UserForm = this.emptyForm();

    readonly roleOptions: { label: string; value: UserRole }[] = [
        { label: 'Client', value: 'customer' },
        { label: 'Commercial', value: 'commercial' },
        { label: 'Administrateur', value: 'admin' },
        { label: 'Gestionnaire (ancien rôle)', value: 'manager' },
        { label: 'Agent (ancien rôle)', value: 'agent' },
        { label: 'Citoyen (ancien rôle)', value: 'citizen' }
    ];

    ngOnInit(): void {
        this.loadUsers();
    }

    get activeCount(): number {
        return this.users().filter((user) => user.is_active).length;
    }

    get customerCount(): number {
        return this.users().filter((user) => user.role === 'customer').length;
    }

    get staffCount(): number {
        return this.users().filter((user) => ['commercial', 'manager'].includes(user.role)).length;
    }

    onSearch(event: Event): void {
        const value = (event.target as HTMLInputElement).value;
        this.usersTable?.filterGlobal(value, 'contains');
    }

    openNew(): void {
        this.editingUser = null;
        this.form = this.emptyForm();
        this.submitted = false;
        this.dialogVisible = true;
    }

    editUser(user: ManagedUser): void {
        this.editingUser = user;
        this.form = {
            name: user.name,
            email: user.email,
            role: user.role as UserRole,
            is_active: user.is_active,
            password: ''
        };
        this.submitted = false;
        this.dialogVisible = true;
    }

    saveUser(): void {
        this.submitted = true;
        const name = this.form.name.trim();
        const email = this.form.email.trim();
        const password = this.form.password;

        if (!name || !email || (!this.editingUser && !this.isStrongPassword(password))) return;

        this.saving.set(true);
        if (!this.editingUser) {
            this.usersApi.create({ name, email, password, role: this.form.role }).subscribe({
                next: () => {
                    this.finishSave('Le compte a été créé.');
                },
                error: (error: unknown) => this.handleSaveError(error),
                complete: () => this.saving.set(false)
            });
            return;
        }

        const changes: UpdateManagedUser = {};
        if (name !== this.editingUser.name) changes['name'] = name;
        if (email !== this.editingUser.email) changes['email'] = email;
        if (this.form.role !== this.editingUser.role && !this.isCurrentUser(this.editingUser)) changes['role'] = this.form.role;
        if (this.form.is_active !== this.editingUser.is_active && !this.isCurrentUser(this.editingUser)) changes['is_active'] = this.form.is_active;
        if (password) {
            if (!this.isStrongPassword(password)) {
                this.saving.set(false);
                return;
            }
            changes['password'] = password;
        }

        if (!Object.keys(changes).length) {
            this.saving.set(false);
            this.dialogVisible = false;
            return;
        }

        this.usersApi.update(this.editingUser.id, changes).subscribe({
            next: () => {
                this.finishSave('Les informations du compte ont été mises à jour.');
            },
            error: (error: unknown) => this.handleSaveError(error),
            complete: () => this.saving.set(false)
        });
    }

    deleteUser(user: ManagedUser): void {
        if (this.isCurrentUser(user)) return;

        this.confirmation.confirm({
            header: 'Supprimer le compte',
            message: `Supprimer le compte de ${user.name} (${user.email}) ? Cette action est définitive.`,
            icon: 'pi pi-exclamation-triangle',
            acceptLabel: 'Supprimer',
            rejectLabel: 'Annuler',
            acceptButtonStyleClass: 'p-button-danger',
            accept: () => this.usersApi.delete(user.id).subscribe({
                next: () => {
                    this.messages.add({ severity: 'success', summary: 'Compte supprimé', detail: user.name, life: 3500 });
                },
                error: (error: unknown) => this.showError(error)
            })
        });
    }

    isCurrentUser(user: ManagedUser): boolean {
        return this.auth.currentUser()?.id === user.id;
    }

    roleLabel(role: string): string {
        return this.roleOptions.find((option) => option.value === role)?.label ?? role;
    }

    roleSeverity(role: string): 'success' | 'info' | 'warn' | 'danger' {
        if (role === 'admin') return 'danger';
        if (role === 'commercial' || role === 'manager') return 'warn';
        if (role === 'customer') return 'info';
        return 'success';
    }

    private loadUsers(): void {
        this.loading.set(true);
        this.usersApi.list().subscribe({
            next: () => undefined,
            error: (error: unknown) => {
                this.loading.set(false);
                this.showError(error);
            },
            complete: () => this.loading.set(false)
        });
    }

    private emptyForm(): UserForm {
        return { name: '', email: '', role: 'customer', is_active: true, password: '' };
    }

    isStrongPassword(password: string): boolean {
        return password.length >= 10 && password.length <= 128 && /[a-z]/.test(password) && /[A-Z]/.test(password) && /\d/.test(password);
    }

    private finishSave(detail: string): void {
        this.saving.set(false);
        this.dialogVisible = false;
        this.messages.add({ severity: 'success', summary: 'Succès', detail, life: 3500 });
    }

    private handleSaveError(error: unknown): void {
        this.saving.set(false);
        this.showError(error);
    }

    private showError(error: unknown): void {
        let detail = 'Une erreur est survenue. Réessayez.';
        if (error instanceof HttpErrorResponse) {
            if (error.status === 401 || error.status === 403) detail = 'Accès réservé à un administrateur connecté.';
            else if (error.status === 409) detail = 'Un compte utilise déjà cette adresse e-mail.';
            else if (typeof error.error?.detail === 'string' && error.error.detail.includes('active administrator')) {
                detail = 'Il faut conserver au moins un administrateur actif.';
            } else if (error.status === 422) detail = 'Vérifie l’adresse e-mail et la politique du mot de passe.';
            else if (error.status === 0) detail = 'Le serveur BazarStore est injoignable.';
        }
        this.messages.add({ severity: 'error', summary: 'Opération impossible', detail, life: 5000 });
    }
}
