import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterModule } from '@angular/router';
import { forkJoin, of, switchMap } from 'rxjs';
import { MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { ToastModule } from 'primeng/toast';
import { CategoryAdminStore, ProductCategory } from '../../core/categories/category-admin.store';

interface StorefrontSettings {
    hero_main_image_key: string | null;
    hero_main_image_url: string | null;
    hero_secondary_image_key: string | null;
    hero_secondary_image_url: string | null;
}

interface UploadedImage { image_key: string; image_url: string; }

@Component({
    selector: 'app-storefront-media',
    standalone: true,
    imports: [CommonModule, RouterModule, ButtonModule, ToastModule],
    templateUrl: './storefront-media.html',
    styleUrl: './storefront-media.css',
    providers: [MessageService]
})
export class StorefrontMedia implements OnInit {
    private readonly http = inject(HttpClient);
    private readonly categoryStore = inject(CategoryAdminStore);
    private readonly messages = inject(MessageService);
    readonly categories = this.categoryStore.categories;
    readonly settings = signal<StorefrontSettings | null>(null);
    readonly saving = signal(false);
    readonly categoryLoadError = signal(false);
    private mainFile: File | null = null;
    private secondaryFile: File | null = null;
    mainPreview: string | null = null;
    secondaryPreview: string | null = null;

    ngOnInit(): void {
        this.categoryStore.list().subscribe({
            next: () => this.categoryLoadError.set(false),
            error: (error: unknown) => {
                this.categoryLoadError.set(true);
                this.notifyHttpError('Chargement des catégories impossible', error);
            }
        });
        this.http.get<StorefrontSettings>('/api/v1/storefront/settings').subscribe({
            next: (settings) => this.settings.set(settings),
            error: (error: unknown) => this.notifyHttpError('Chargement des visuels impossible', error)
        });
    }

    selectHero(event: Event, target: 'main' | 'secondary'): void {
        const input = event.target as HTMLInputElement;
        const file = input.files?.[0];
        if (!file) return;
        if (!this.validImage(file)) {
            this.messages.add({ severity: 'error', summary: 'Image invalide', detail: 'Choisis une image JPEG, PNG, GIF ou WebP de 5 Mo maximum.' });
            input.value = '';
            return;
        }
        if (target === 'main') {
            this.mainFile = file;
            this.mainPreview = URL.createObjectURL(file);
        } else {
            this.secondaryFile = file;
            this.secondaryPreview = URL.createObjectURL(file);
        }
    }

    saveHero(): void {
        const jobs = [
            this.mainFile ? this.upload(this.mainFile, 'storefront') : null,
            this.secondaryFile ? this.upload(this.secondaryFile, 'storefront') : null
        ];
        if (!jobs.some(Boolean)) return;
        this.saving.set(true);
        const uploads = jobs.map((job) => job ?? of(null));
        forkJoin(uploads).subscribe({
            next: ([main, secondary]) => {
                const payload = {
                    ...(main ? { hero_main_image_key: main.image_key } : {}),
                    ...(secondary ? { hero_secondary_image_key: secondary.image_key } : {})
                };
                this.http.patch<StorefrontSettings>('/api/v1/storefront/settings', payload).subscribe({
                    next: (settings) => {
                        this.settings.set(settings);
                        this.mainFile = this.secondaryFile = null;
                        this.mainPreview = this.secondaryPreview = null;
                        this.saving.set(false);
                        this.messages.add({ severity: 'success', summary: 'Images mises à jour', detail: 'Les visuels de la page d’accueil sont enregistrés.' });
                    },
                    error: (error: unknown) => { this.saving.set(false); this.notifyHttpError('Enregistrement des visuels impossible', error); }
                });
            },
            error: (error: unknown) => { this.saving.set(false); this.notifyHttpError('Téléversement de l’image impossible', error); }
        });
    }

    selectCategoryImage(event: Event, category: ProductCategory): void {
        const input = event.target as HTMLInputElement;
        const file = input.files?.[0];
        if (!file) return;
        if (!this.validImage(file)) {
            this.notifyError('Choisis une image JPEG, PNG, GIF ou WebP de 5 Mo maximum.');
            input.value = '';
            return;
        }
        this.saving.set(true);
        this.upload(file, 'categories').pipe(
            switchMap((image) => this.categoryStore.update(category.id, { image_key: image.image_key }))
        ).subscribe({
            next: () => { this.saving.set(false); this.messages.add({ severity: 'success', summary: 'Image enregistrée', detail: category.name }); },
            error: (error: unknown) => { this.saving.set(false); this.notifyHttpError(`Image de « ${category.name} » non enregistrée`, error); }
        });
    }

    imageUrl(category: ProductCategory): string | null { return category.image_url; }

    private upload(file: File, kind: 'storefront' | 'categories') {
        const body = new FormData();
        body.append('file', file, file.name);
        return this.http.post<UploadedImage>(`/api/v1/storefront/images?kind=${kind}`, body);
    }

    private validImage(file: File): boolean {
        return ['image/jpeg', 'image/png', 'image/gif', 'image/webp'].includes(file.type) && file.size <= 5 * 1024 * 1024;
    }

    private notifyError(detail: string): void { this.messages.add({ severity: 'error', summary: 'Opération impossible', detail, life: 5000 }); }

    private notifyHttpError(summary: string, error: unknown): void {
        if (!(error instanceof HttpErrorResponse)) {
            this.notifyError(summary);
            return;
        }
        const detail = typeof error.error?.detail === 'string'
            ? error.error.detail
            : error.status === 0
                ? 'API inaccessible. Vérifie que le backend et PostgreSQL sont démarrés.'
                : `Réponse HTTP ${error.status}. Vérifie les logs du backend.`;
        this.messages.add({ severity: 'error', summary, detail, life: 8000 });
    }
}
