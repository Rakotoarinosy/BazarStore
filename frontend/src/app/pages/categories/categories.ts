import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, ViewChild, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ConfirmationService, MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { Table, TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { ToastModule } from 'primeng/toast';
import { ToolbarModule } from 'primeng/toolbar';
import { CategoryAdminStore, ProductCategory, UpdateProductCategory } from '../../core/categories/category-admin.store';

interface CategoryForm {
    name: string;
    slug: string;
    description: string;
    is_active: boolean;
}

@Component({
    selector: 'app-categories',
    standalone: true,
    imports: [CommonModule, FormsModule, TableModule, ToolbarModule, ButtonModule, DialogModule, InputTextModule, TagModule, ToastModule, ConfirmDialogModule],
    templateUrl: './categories.html',
    styleUrl: './categories.css',
    providers: [ConfirmationService, MessageService]
})
export class Categories implements OnInit {
    private readonly categoriesApi = inject(CategoryAdminStore);
    private readonly confirmation = inject(ConfirmationService);
    private readonly messages = inject(MessageService);

    @ViewChild('categoriesTable') categoriesTable?: Table;

    readonly categories = this.categoriesApi.categories;
    readonly loading = signal(false);
    readonly saving = signal(false);
    dialogVisible = false;
    submitted = false;
    editingCategory: ProductCategory | null = null;
    form: CategoryForm = this.emptyForm();

    ngOnInit(): void {
        this.loadCategories();
    }

    get activeCount(): number {
        return this.categories().filter((category) => category.is_active).length;
    }

    get inactiveCount(): number {
        return this.categories().filter((category) => !category.is_active).length;
    }

    onSearch(event: Event): void {
        this.categoriesTable?.filterGlobal((event.target as HTMLInputElement).value, 'contains');
    }

    openNew(): void {
        this.editingCategory = null;
        this.form = this.emptyForm();
        this.submitted = false;
        this.dialogVisible = true;
    }

    editCategory(category: ProductCategory): void {
        this.editingCategory = category;
        this.form = {
            name: category.name,
            slug: category.slug,
            description: category.description,
            is_active: category.is_active
        };
        this.submitted = false;
        this.dialogVisible = true;
    }

    saveCategory(): void {
        this.submitted = true;
        const name = this.form.name.trim();
        if (name.length < 2) return;

        const payload = {
            name,
            ...(this.form.slug.trim() ? { slug: this.form.slug.trim() } : {}),
            description: this.form.description.trim(),
            is_active: this.form.is_active
        };
        this.saving.set(true);

        const request = this.editingCategory
            ? this.categoriesApi.update(this.editingCategory.id, payload as UpdateProductCategory)
            : this.categoriesApi.create(payload);

        request.subscribe({
            next: () => {
                this.saving.set(false);
                this.dialogVisible = false;
                this.messages.add({ severity: 'success', summary: 'Succès', detail: this.editingCategory ? 'La catégorie a été mise à jour.' : 'La catégorie a été créée.', life: 3500 });
            },
            error: (error: unknown) => {
                this.saving.set(false);
                this.showError(error);
            }
        });
    }

    deleteCategory(category: ProductCategory): void {
        this.confirmation.confirm({
            header: 'Supprimer la catégorie',
            message: `Supprimer « ${category.name} » ? Cette action est définitive.`,
            icon: 'pi pi-exclamation-triangle',
            acceptLabel: 'Supprimer',
            rejectLabel: 'Annuler',
            acceptButtonStyleClass: 'p-button-danger',
            accept: () => this.categoriesApi.delete(category.id).subscribe({
                next: () => this.messages.add({ severity: 'success', summary: 'Catégorie supprimée', detail: category.name, life: 3500 }),
                error: (error: unknown) => this.showError(error)
            })
        });
    }

    private loadCategories(): void {
        this.loading.set(true);
        this.categoriesApi.list().subscribe({
            error: (error: unknown) => {
                this.loading.set(false);
                this.showError(error);
            },
            complete: () => this.loading.set(false)
        });
    }

    private emptyForm(): CategoryForm {
        return { name: '', slug: '', description: '', is_active: true };
    }

    private showError(error: unknown): void {
        let detail = 'Une erreur est survenue. Réessaie.';
        if (error instanceof HttpErrorResponse) {
            if (error.status === 401 || error.status === 403) detail = 'La gestion des catégories est réservée aux administrateurs.';
            else if (error.status === 409) detail = 'Ce slug est déjà utilisé ou la catégorie est encore associée à des produits.';
            else if (error.status === 422) detail = 'Vérifie le nom et les informations de la catégorie.';
            else if (error.status === 0) detail = 'Le serveur BazarStore est injoignable.';
        }
        this.messages.add({ severity: 'error', summary: 'Opération impossible', detail, life: 5000 });
    }
}
