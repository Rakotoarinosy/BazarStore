import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, ViewChild, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { catchError, of, switchMap, throwError } from 'rxjs';
import { ConfirmationService, MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { Table, TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { ToastModule } from 'primeng/toast';
import { ToolbarModule } from 'primeng/toolbar';
import { CategoryAdminStore, ProductCategory } from '../../core/categories/category-admin.store';
import { CreateProduct, ManagedProduct, ProductAdminStore, UpdateProduct } from '../../core/products/product-admin.store';

interface ProductForm {
    code: string;
    name: string;
    description: string;
    price: number | null;
    quantity: number | null;
    image_url: string;
    image_key: string | null;
    category_id: string;
    is_active: boolean;
}

@Component({
    selector: 'app-products',
    standalone: true,
    imports: [CommonModule, FormsModule, TableModule, ToolbarModule, ButtonModule, DialogModule, InputTextModule, TagModule, ToastModule, ConfirmDialogModule],
    templateUrl: './products.html',
    styleUrl: './products.css',
    providers: [ConfirmationService, MessageService]
})
export class Products implements OnInit {
    private readonly productsApi = inject(ProductAdminStore);
    private readonly categoriesApi = inject(CategoryAdminStore);
    private readonly confirmation = inject(ConfirmationService);
    private readonly messages = inject(MessageService);

    @ViewChild('productsTable') productsTable?: Table;

    readonly products = this.productsApi.products;
    readonly categories = this.categoriesApi.categories;
    readonly loading = this.productsApi.loading;
    readonly saving = signal(false);
    readonly activeCategories = () => this.categories().filter((category) => category.is_active);
    dialogVisible = false;
    submitted = false;
    editingProduct: ManagedProduct | null = null;
    form: ProductForm = this.emptyForm();
    selectedImage: File | null = null;
    private previewUrl: string | null = null;

    ngOnInit(): void {
        this.categoriesApi.list().subscribe({ error: (error: unknown) => this.showError(error) });
        this.productsApi.list().subscribe({ error: (error: unknown) => this.showError(error) });
    }

    get activeCount(): number {
        return this.products().filter((product) => product.is_active).length;
    }

    get outOfStockCount(): number {
        return this.products().filter((product) => product.quantity === 0).length;
    }

    onSearch(event: Event): void {
        this.productsTable?.filterGlobal((event.target as HTMLInputElement).value, 'contains');
    }

    openNew(): void {
        this.editingProduct = null;
        this.form = { ...this.emptyForm(), category_id: this.activeCategories()[0]?.id ?? '' };
        this.selectedImage = null;
        this.submitted = false;
        this.dialogVisible = true;
    }

    editProduct(product: ManagedProduct): void {
        this.editingProduct = product;
        this.form = {
            code: product.code,
            name: product.name,
            description: product.description,
            price: product.price,
            quantity: product.quantity,
            image_url: product.image_url ?? '',
            image_key: product.image_key,
            category_id: product.category_id,
            is_active: product.is_active
        };
        this.selectedImage = null;
        this.submitted = false;
        this.dialogVisible = true;
    }

    saveProduct(): void {
        this.submitted = true;
        const code = this.form.code.trim();
        const name = this.form.name.trim();
        const price = Number(this.form.price);
        const quantity = Number(this.form.quantity);
        if (code.length < 2 || name.length < 2 || !this.form.category_id || !Number.isInteger(price) || price < 0 || !Number.isInteger(quantity) || quantity < 0) return;

        const payload: CreateProduct = {
            code,
            name,
            description: this.form.description.trim(),
            price,
            quantity,
            image_url: this.form.image_key ? null : this.form.image_url.trim() || null,
            image_key: this.form.image_key,
            category_id: this.form.category_id,
            is_active: this.form.is_active
        };
        this.saving.set(true);

        const saveWithImage = (imageKey: string | null) => {
            const productPayload = { ...payload, image_key: imageKey, image_url: imageKey ? null : payload.image_url };
            return this.editingProduct
                ? this.productsApi.update(this.editingProduct.id, this.changedFields(productPayload, this.editingProduct))
                : this.productsApi.create(productPayload);
        };
        const request = this.selectedImage
            ? this.productsApi.uploadImage(this.selectedImage).pipe(
                switchMap((image) => saveWithImage(image.image_key).pipe(
                    catchError((error: unknown) => this.productsApi.deleteImage(image.image_key).pipe(
                        catchError(() => of(undefined)),
                        switchMap(() => throwError(() => error))
                    ))
                ))
            )
            : saveWithImage(payload.image_key);

        request.subscribe({
            next: () => {
                this.saving.set(false);
                this.dialogVisible = false;
                this.clearImagePreview();
                this.selectedImage = null;
                this.messages.add({ severity: 'success', summary: 'Succès', detail: this.editingProduct ? 'Le produit a été mis à jour.' : 'Le produit a été créé.', life: 3500 });
            },
            error: (error: unknown) => {
                this.saving.set(false);
                this.showError(error);
            }
        });
    }

    deleteProduct(product: ManagedProduct): void {
        this.confirmation.confirm({
            header: 'Supprimer le produit',
            message: `Supprimer « ${product.name} » (${product.code}) ? Cette action est définitive.`,
            icon: 'pi pi-exclamation-triangle',
            acceptLabel: 'Supprimer',
            rejectLabel: 'Annuler',
            acceptButtonStyleClass: 'p-button-danger',
            accept: () => this.productsApi.delete(product.id).subscribe({
                next: () => this.messages.add({ severity: 'success', summary: 'Produit supprimé', detail: product.name, life: 3500 }),
                error: (error: unknown) => this.showError(error)
            })
        });
    }

    selectImage(event: Event): void {
        const file = (event.target as HTMLInputElement).files?.[0] ?? null;
        if (!file) return;
        if (!['image/jpeg', 'image/png', 'image/gif', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) {
            this.messages.add({ severity: 'error', summary: 'Image invalide', detail: 'Choisis une image JPEG, PNG, GIF ou WebP de 5 Mo maximum.', life: 5000 });
            (event.target as HTMLInputElement).value = '';
            return;
        }
        this.clearImagePreview();
        this.selectedImage = file;
        this.previewUrl = URL.createObjectURL(file);
        this.form.image_url = this.previewUrl;
    }

    removeImage(): void {
        this.selectedImage = null;
        this.clearImagePreview();
        this.form.image_url = '';
        this.form.image_key = null;
    }

    stockSeverity(status: ManagedProduct['inventory_status']): 'success' | 'warn' | 'danger' {
        return status === 'OUTOFSTOCK' ? 'danger' : status === 'LOWSTOCK' ? 'warn' : 'success';
    }

    stockLabel(status: ManagedProduct['inventory_status']): string {
        return status === 'OUTOFSTOCK' ? 'Épuisé' : status === 'LOWSTOCK' ? 'Stock faible' : 'En stock';
    }

    formatPrice(price: number): string {
        return `${new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 }).format(price)} Ar`;
    }

    categoryName(categoryId: string): string {
        return this.categories().find((category) => category.id === categoryId)?.name ?? 'Catégorie indisponible';
    }

    private emptyForm(): ProductForm {
        return { code: '', name: '', description: '', price: null, quantity: 0, image_url: '', image_key: null, category_id: '', is_active: true };
    }

    private changedFields(payload: CreateProduct, current: ManagedProduct): UpdateProduct {
        const changes: UpdateProduct = {};
        for (const field of ['code', 'name', 'description', 'price', 'quantity', 'image_url', 'image_key', 'category_id', 'is_active'] as const) {
            if (payload[field] !== current[field]) changes[field] = payload[field] as never;
        }
        return changes;
    }

    private clearImagePreview(): void {
        if (this.previewUrl) URL.revokeObjectURL(this.previewUrl);
        this.previewUrl = null;
    }

    private showError(error: unknown): void {
        let detail = 'Une erreur est survenue. Réessaie.';
        if (error instanceof HttpErrorResponse) {
            if (error.status === 401 || error.status === 403) detail = 'La gestion du catalogue est réservée aux administrateurs.';
            else if (error.status === 404) detail = 'La catégorie choisie n’existe plus. Recharge les données et réessaie.';
            else if (error.status === 400) detail = 'Le fichier doit être une image JPEG, PNG, GIF ou WebP de 5 Mo maximum.';
            else if (error.status === 409) detail = 'Ce code produit est déjà utilisé.';
            else if (error.status === 503) detail = 'MinIO ne répond pas ou ses identifiants ne sont pas configurés dans backend/.env.';
            else if (error.status === 422) detail = 'Vérifie le code, le nom, le prix, le stock et la catégorie.';
            else if (error.status === 0) detail = 'Le serveur BazarStore est injoignable.';
        }
        this.messages.add({ severity: 'error', summary: 'Opération impossible', detail, life: 5000 });
    }
}
