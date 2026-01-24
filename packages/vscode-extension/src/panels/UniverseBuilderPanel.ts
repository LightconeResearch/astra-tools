import * as vscode from 'vscode';
import * as path from 'path';
import { AspParser } from '../services/AspParser';
import { ConstraintGraph } from '../services/ConstraintGraph';

export class UniverseBuilderPanel {
  public static currentPanel: UniverseBuilderPanel | undefined;
  private static readonly viewType = 'asp.universeBuilder';

  private readonly panel: vscode.WebviewPanel;
  private readonly extensionUri: vscode.Uri;
  private aspFile: vscode.Uri;
  private disposables: vscode.Disposable[] = [];

  public static createOrShow(extensionUri: vscode.Uri, aspFile: vscode.Uri) {
    const column = vscode.ViewColumn.Beside;

    if (UniverseBuilderPanel.currentPanel) {
      UniverseBuilderPanel.currentPanel.panel.reveal(column);
      UniverseBuilderPanel.currentPanel.aspFile = aspFile;
      UniverseBuilderPanel.currentPanel.loadAnalysis();
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      UniverseBuilderPanel.viewType,
      'Universe Builder',
      column,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [
          vscode.Uri.joinPath(extensionUri, 'dist', 'webview'),
          vscode.Uri.joinPath(extensionUri, 'media'),
        ],
      }
    );

    UniverseBuilderPanel.currentPanel = new UniverseBuilderPanel(panel, extensionUri, aspFile);
  }

  public static update(uri: vscode.Uri) {
    if (UniverseBuilderPanel.currentPanel?.aspFile.fsPath === uri.fsPath) {
      UniverseBuilderPanel.currentPanel.loadAnalysis();
    }
  }

  private constructor(panel: vscode.WebviewPanel, extensionUri: vscode.Uri, aspFile: vscode.Uri) {
    this.panel = panel;
    this.extensionUri = extensionUri;
    this.aspFile = aspFile;

    this.updateHtml();
    this.loadAnalysis();

    this.panel.onDidDispose(() => this.dispose(), null, this.disposables);

    this.panel.webview.onDidReceiveMessage(
      message => this.handleMessage(message),
      null,
      this.disposables
    );
  }

  private async loadAnalysis() {
    const parser = new AspParser();
    const result = await parser.parseFile(this.aspFile.fsPath);

    if (!result.analysis) {
      this.panel.webview.postMessage({
        type: 'error',
        message: 'Failed to parse analysis',
        errors: result.errors,
      });
      return;
    }

    // Build constraint graph
    const constraintGraph = new ConstraintGraph(result.analysis);
    const constraints = constraintGraph.getConstraints();

    // Load existing universes
    const universes = await this.loadExistingUniverses();

    this.panel.webview.postMessage({
      type: 'analysisLoaded',
      data: result.analysis,
      constraints,
      universes,
      errors: result.errors,
      filePath: this.aspFile.fsPath,
    });
  }

  private async loadExistingUniverses(): Promise<{ name: string; selections: Record<string, string> }[]> {
    const universesDir = path.join(path.dirname(this.aspFile.fsPath), 'universes');
    const universes: { name: string; selections: Record<string, string> }[] = [];

    try {
      const files = await vscode.workspace.fs.readDirectory(vscode.Uri.file(universesDir));

      for (const [filename, type] of files) {
        if (type === vscode.FileType.File && filename.endsWith('.yaml')) {
          const filePath = path.join(universesDir, filename);
          const content = await vscode.workspace.fs.readFile(vscode.Uri.file(filePath));
          const yaml = await import('js-yaml');
          const data = yaml.load(content.toString()) as { selections?: Record<string, string> };

          if (data?.selections) {
            universes.push({
              name: filename.replace('.yaml', ''),
              selections: data.selections,
            });
          }
        }
      }
    } catch {
      // Universes directory might not exist
    }

    return universes;
  }

  private async handleMessage(message: { type: string; [key: string]: unknown }) {
    switch (message.type) {
      case 'ready':
        this.loadAnalysis();
        break;

      case 'validateUniverse':
        await this.validateUniverse(message.selections as Record<string, string>);
        break;

      case 'saveUniverse':
        await this.saveUniverse(
          message.name as string,
          message.selections as Record<string, string>
        );
        break;

      case 'getValidOptions':
        await this.getValidOptions(
          message.decisionId as string,
          message.currentSelections as Record<string, string>
        );
        break;
    }
  }

  private async validateUniverse(selections: Record<string, string>) {
    const parser = new AspParser();
    const result = await parser.parseFile(this.aspFile.fsPath);

    if (!result.analysis) {
      this.panel.webview.postMessage({
        type: 'validationResult',
        valid: false,
        errors: ['Failed to parse analysis'],
      });
      return;
    }

    const constraintGraph = new ConstraintGraph(result.analysis);
    const violations = constraintGraph.validateSelections(selections);

    this.panel.webview.postMessage({
      type: 'validationResult',
      valid: violations.length === 0,
      errors: violations,
    });
  }

  private async getValidOptions(decisionId: string, currentSelections: Record<string, string>) {
    const parser = new AspParser();
    const result = await parser.parseFile(this.aspFile.fsPath);

    if (!result.analysis) {
      return;
    }

    const constraintGraph = new ConstraintGraph(result.analysis);
    const validOptions = constraintGraph.getValidOptions(decisionId, currentSelections);

    this.panel.webview.postMessage({
      type: 'validOptions',
      decisionId,
      options: validOptions,
    });
  }

  private async saveUniverse(name: string, selections: Record<string, string>) {
    const universesDir = path.join(path.dirname(this.aspFile.fsPath), 'universes');
    const filePath = path.join(universesDir, `${name}.yaml`);

    const yaml = await import('js-yaml');
    const content = yaml.dump({ selections }, { lineWidth: 100 });

    try {
      await vscode.workspace.fs.createDirectory(vscode.Uri.file(universesDir));
    } catch {
      // Directory might already exist
    }

    await vscode.workspace.fs.writeFile(
      vscode.Uri.file(filePath),
      Buffer.from(content)
    );

    vscode.window.showInformationMessage(`Universe "${name}" saved`);
    this.loadAnalysis(); // Reload to show new universe
  }

  private updateHtml() {
    const webview = this.panel.webview;

    const scriptUri = webview.asWebviewUri(
      vscode.Uri.joinPath(this.extensionUri, 'dist', 'webview', 'universeBuilder.js')
    );
    const styleUri = webview.asWebviewUri(
      vscode.Uri.joinPath(this.extensionUri, 'dist', 'webview', 'style.css')
    );

    // CSP must allow the webview source for ES module imports
    this.panel.webview.html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource} 'unsafe-inline'; script-src ${webview.cspSource}; font-src ${webview.cspSource};">
  <link href="${styleUri}" rel="stylesheet">
  <title>Universe Builder</title>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="${scriptUri}"></script>
</body>
</html>`;
  }

  public dispose() {
    UniverseBuilderPanel.currentPanel = undefined;
    this.panel.dispose();

    while (this.disposables.length) {
      const d = this.disposables.pop();
      if (d) {
        d.dispose();
      }
    }
  }
}

function getNonce() {
  let text = '';
  const possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  for (let i = 0; i < 32; i++) {
    text += possible.charAt(Math.floor(Math.random() * possible.length));
  }
  return text;
}
