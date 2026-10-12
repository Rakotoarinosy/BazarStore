import { Component, HostListener, input, signal } from '@angular/core';

/**
 * Bouton flottant « Retour en haut », affiché une fois la page défilée
 * au-delà de `threshold` pixels.
 */
@Component({
    selector: 'app-scroll-top-button',
    standalone: true,
    template: `
        <button type="button" class="scroll-top-button" aria-label="Retour en haut" [class.visible]="visible()" [attr.tabindex]="visible() ? null : -1" [attr.aria-hidden]="!visible()" (click)="scrollToTop()">
            <span>Retour en haut</span>
            <i class="pi pi-arrow-up" aria-hidden="true"></i>
        </button>
    `,
    styles: `
        .scroll-top-button {
            position: fixed;
            z-index: 30;
            right: 1.5rem;
            bottom: 1.5rem;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.7rem 1rem;
            border: 1px solid #e6e9ef;
            border-radius: 999px;
            background: #fff;
            box-shadow: 0 10px 30px rgb(23 39 68 / 14%);
            color: var(--brand-blue, #315e91);
            font: 600 0.75rem 'Plus Jakarta Sans', sans-serif;
            cursor: pointer;
            opacity: 0;
            pointer-events: none;
            transform: translateY(0.75rem);
            transition: opacity 0.2s ease, transform 0.2s ease, background-color 0.2s ease;
        }

        .scroll-top-button.visible {
            opacity: 1;
            pointer-events: auto;
            transform: translateY(0);
        }

        .scroll-top-button:hover {
            background: var(--brand-navy, #172744);
            color: #fff;
        }

        .scroll-top-button:focus-visible {
            outline: 2px solid var(--brand-orange, #e8893d);
            outline-offset: 2px;
        }

        .scroll-top-button i {
            font-size: 0.9rem;
        }

        @media (max-width: 640px) {
            .scroll-top-button {
                right: 1rem;
                bottom: 1rem;
                padding: 0.75rem;
            }

            .scroll-top-button span {
                display: none;
            }
        }

        @media (prefers-reduced-motion: reduce) {
            .scroll-top-button {
                transition: none;
            }
        }
    `
})
export class ScrollTopButton {
    readonly threshold = input(400);
    readonly visible = signal(false);

    @HostListener('window:scroll')
    onScroll(): void {
        this.visible.set(window.scrollY > this.threshold());
    }

    scrollToTop(): void {
        const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        window.scrollTo({ top: 0, behavior: reduceMotion ? 'auto' : 'smooth' });
    }
}
