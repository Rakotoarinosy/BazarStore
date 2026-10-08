import { Component, inject, OnInit, signal } from '@angular/core';
import { TreeNode } from 'primeng/api';
import { TreeModule } from 'primeng/tree';
import { FormsModule } from '@angular/forms';
import { TreeTableModule } from 'primeng/treetable';
import { CommonModule } from '@angular/common';
import { NodeService } from '@/app/pages/service/node.service';

@Component({
    selector: 'app-tree-demo',
    standalone: true,
    imports: [CommonModule, FormsModule, TreeModule, TreeTableModule],
    templateUrl: './treedemo.html',
    providers: [NodeService]
})
export class TreeDemo implements OnInit {
    treeValue = signal<TreeNode[]>([]);

    treeTableValue = signal<TreeNode[]>([]);

    selectedTreeValue: TreeNode[] = [];

    selectedTreeTableValue = {};

    cols: any[] = [];

    nodeService = inject(NodeService);

    ngOnInit() {
        this.nodeService.getFiles().then((files) => this.treeValue.set(files));
        this.nodeService.getTreeTableNodes().then((files: any) => this.treeTableValue.set(files));

        this.cols = [
            { field: 'name', header: 'Name' },
            { field: 'size', header: 'Size' },
            { field: 'type', header: 'Type' }
        ];

        this.selectedTreeTableValue = {
            '0-0': {
                partialChecked: false,
                checked: true
            }
        };
    }
}
