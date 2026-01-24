import * as vscode from 'vscode';
import { AspParser } from './services/AspParser';
import { FileWatcher } from './services/FileWatcher';
import { VisualizationPanel } from './panels/VisualizationPanel';
import { UniverseBuilderPanel } from './panels/UniverseBuilderPanel';

let fileWatcher: FileWatcher | undefined;

export function activate(context: vscode.ExtensionContext) {
  console.log('ASP extension activated');

  // Initialize file watcher
  fileWatcher = new FileWatcher();
  context.subscriptions.push(fileWatcher);

  // Register commands
  context.subscriptions.push(
    vscode.commands.registerCommand('asp.openVisualization', async (uri?: vscode.Uri) => {
      const aspFile = uri || await findAspFile();
      if (!aspFile) {
        vscode.window.showWarningMessage('No asp.yaml file found in workspace');
        return;
      }
      VisualizationPanel.createOrShow(context.extensionUri, aspFile);
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('asp.validateAnalysis', async (uri?: vscode.Uri) => {
      const aspFile = uri || await findAspFile();
      if (!aspFile) {
        vscode.window.showWarningMessage('No asp.yaml file found in workspace');
        return;
      }

      const parser = new AspParser();
      const result = await parser.parseFile(aspFile.fsPath);

      if (result.errors.length === 0) {
        vscode.window.showInformationMessage('ASP analysis is valid');
      } else {
        const diagnostics = result.errors.map(e =>
          `${e.type}: ${e.message}${e.path ? ` at ${e.path}` : ''}`
        );
        vscode.window.showErrorMessage(
          `ASP validation failed:\n${diagnostics.join('\n')}`
        );
      }
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('asp.openUniverseBuilder', async (uri?: vscode.Uri) => {
      const aspFile = uri || await findAspFile();
      if (!aspFile) {
        vscode.window.showWarningMessage('No asp.yaml file found in workspace');
        return;
      }
      UniverseBuilderPanel.createOrShow(context.extensionUri, aspFile);
    })
  );

  // Set up file watcher for validation on save
  const config = vscode.workspace.getConfiguration('asp');
  if (config.get<boolean>('autoValidate', true)) {
    context.subscriptions.push(
      vscode.workspace.onDidSaveTextDocument(document => {
        if (document.fileName.endsWith('asp.yaml')) {
          vscode.commands.executeCommand('asp.validateAnalysis', vscode.Uri.file(document.fileName));
        }
      })
    );
  }

  // Provide analysis context to webview panels when files change
  fileWatcher.onDidChange(uri => {
    VisualizationPanel.update(uri);
    UniverseBuilderPanel.update(uri);
  });
}

export function deactivate() {
  fileWatcher?.dispose();
}

async function findAspFile(): Promise<vscode.Uri | undefined> {
  // First check if active editor is asp.yaml
  const activeEditor = vscode.window.activeTextEditor;
  if (activeEditor?.document.fileName.endsWith('asp.yaml')) {
    return vscode.Uri.file(activeEditor.document.fileName);
  }

  // Search workspace for asp.yaml files
  const files = await vscode.workspace.findFiles('**/asp.yaml', '**/node_modules/**', 1);
  return files[0];
}
