import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';

@Component({
    selector: 'app-documentation',
    standalone: true,
    imports: [CommonModule],
    templateUrl: './documentation.html',
    styleUrl: './documentation.scss'
})
export class Documentation {}
