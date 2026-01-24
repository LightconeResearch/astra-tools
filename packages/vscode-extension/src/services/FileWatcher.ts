import * as vscode from 'vscode';

/**
 * Watches for changes to asp.yaml files in the workspace.
 */
export class FileWatcher implements vscode.Disposable {
  private watcher: vscode.FileSystemWatcher;
  private changeEmitter = new vscode.EventEmitter<vscode.Uri>();
  private deleteEmitter = new vscode.EventEmitter<vscode.Uri>();
  private createEmitter = new vscode.EventEmitter<vscode.Uri>();

  public readonly onDidChange = this.changeEmitter.event;
  public readonly onDidDelete = this.deleteEmitter.event;
  public readonly onDidCreate = this.createEmitter.event;

  constructor() {
    // Watch for asp.yaml files and universe files
    this.watcher = vscode.workspace.createFileSystemWatcher(
      '**/{asp.yaml,universes/*.yaml}'
    );

    this.watcher.onDidChange(uri => {
      this.changeEmitter.fire(uri);
    });

    this.watcher.onDidDelete(uri => {
      this.deleteEmitter.fire(uri);
    });

    this.watcher.onDidCreate(uri => {
      this.createEmitter.fire(uri);
    });
  }

  dispose() {
    this.watcher.dispose();
    this.changeEmitter.dispose();
    this.deleteEmitter.dispose();
    this.createEmitter.dispose();
  }
}
