import * as vscode from 'vscode';
import { AspParser } from '../services/AspParser';
import { YamlLocator } from '../services/YamlLocator';

export class VisualizationPanel {
  public static currentPanel: VisualizationPanel | undefined;
  private static readonly viewType = 'asp.visualization';

  private readonly panel: vscode.WebviewPanel;
  private readonly extensionUri: vscode.Uri;
  private aspFile: vscode.Uri;
  private disposables: vscode.Disposable[] = [];

  public static createOrShow(extensionUri: vscode.Uri, aspFile: vscode.Uri) {
    const column = vscode.window.activeTextEditor
      ? vscode.window.activeTextEditor.viewColumn
      : undefined;

    // If we already have a panel, show it
    if (VisualizationPanel.currentPanel) {
      VisualizationPanel.currentPanel.panel.reveal(column);
      VisualizationPanel.currentPanel.aspFile = aspFile;
      VisualizationPanel.currentPanel.loadAnalysis();
      return;
    }

    // Create a new panel
    const panel = vscode.window.createWebviewPanel(
      VisualizationPanel.viewType,
      'ASP Visualization',
      column || vscode.ViewColumn.One,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [
          vscode.Uri.joinPath(extensionUri, 'dist', 'webview'),
          vscode.Uri.joinPath(extensionUri, 'media'),
        ],
      }
    );

    VisualizationPanel.currentPanel = new VisualizationPanel(panel, extensionUri, aspFile);
  }

  public static update(uri: vscode.Uri) {
    if (VisualizationPanel.currentPanel?.aspFile.fsPath === uri.fsPath) {
      VisualizationPanel.currentPanel.loadAnalysis();
    }
  }

  private constructor(panel: vscode.WebviewPanel, extensionUri: vscode.Uri, aspFile: vscode.Uri) {
    this.panel = panel;
    this.extensionUri = extensionUri;
    this.aspFile = aspFile;

    // Set the webview's initial html content
    this.updateHtml();
    this.loadAnalysis();

    // Listen for when the panel is disposed
    this.panel.onDidDispose(() => this.dispose(), null, this.disposables);

    // Handle messages from the webview
    this.panel.webview.onDidReceiveMessage(
      message => this.handleMessage(message),
      null,
      this.disposables
    );
  }

  private async loadAnalysis() {
    const parser = new AspParser();
    const result = await parser.parseFile(this.aspFile.fsPath);

    this.panel.webview.postMessage({
      type: 'analysisLoaded',
      data: result.analysis,
      errors: result.errors,
      filePath: this.aspFile.fsPath,
    });
  }

  private async handleMessage(message: { type: string; [key: string]: unknown }) {
    switch (message.type) {
      case 'ready':
        this.loadAnalysis();
        break;

      case 'updateField':
        await this.updateField(
          message.path as string[],
          message.value as string
        );
        break;

      case 'selectElement':
        // Select the element in the YAML file (without stealing focus)
        await this.selectElementInEditor(message.element as {
          type: string;
          decisionId?: string;
          optionId?: string;
          inputId?: string;
          outputId?: string;
        });
        break;

      case 'openFile':
        const doc = await vscode.workspace.openTextDocument(this.aspFile);
        await vscode.window.showTextDocument(doc, {
          selection: message.range ? new vscode.Range(
            (message.range as { start: { line: number; character: number } }).start.line,
            (message.range as { start: { line: number; character: number } }).start.character,
            (message.range as { end: { line: number; character: number } }).end.line,
            (message.range as { end: { line: number; character: number } }).end.character
          ) : undefined,
        });
        break;
    }
  }

  /**
   * Select the relevant lines in asp.yaml when user clicks on an element.
   * This makes the selection visible to Claude Code automatically.
   * Does NOT steal focus from the visualization panel.
   */
  private async selectElementInEditor(element: {
    type: string;
    decisionId?: string;
    optionId?: string;
    inputId?: string;
    outputId?: string;
  }) {
    const locator = new YamlLocator();
    await locator.loadFile(this.aspFile.fsPath);

    let location: { startLine: number; endLine: number } | null = null;

    switch (element.type) {
      case 'decision':
        if (element.decisionId) {
          location = locator.findDecision(element.decisionId);
        }
        break;

      case 'option':
        if (element.decisionId && element.optionId) {
          location = locator.findOption(element.decisionId, element.optionId);
        }
        break;

      case 'input':
        if (element.inputId) {
          location = locator.findInput(element.inputId);
        }
        break;

      case 'output':
        if (element.outputId) {
          location = locator.findOutput(element.outputId);
        }
        break;

      case 'analysis':
        location = locator.findAnalysis();
        break;
    }

    if (!location) return;

    const doc = await vscode.workspace.openTextDocument(this.aspFile);

    // Check if file is already open in a visible editor
    let editor = vscode.window.visibleTextEditors.find(
      e => e.document.uri.fsPath === this.aspFile.fsPath
    );

    if (!editor) {
      // Open the file in the background (ViewColumn.Beside keeps it separate)
      editor = await vscode.window.showTextDocument(doc, {
        viewColumn: vscode.ViewColumn.One,
        preserveFocus: true,
        preview: true,
      });
    }

    // Create selection covering the element's lines
    const startPos = new vscode.Position(location.startLine, 0);
    const endPos = new vscode.Position(location.endLine, doc.lineAt(location.endLine).text.length);
    const selection = new vscode.Selection(startPos, endPos);

    // Set selection without revealing (no scroll, no focus change)
    editor.selection = selection;
  }

  private async updateField(path: string[], value: string) {
    const { YamlWriter } = await import('../services/YamlWriter');
    const writer = new YamlWriter();

    try {
      await writer.updateField(this.aspFile.fsPath, path, value);
    } catch (error) {
      vscode.window.showErrorMessage(`Failed to update field: ${error}`);
    }
  }

  private updateHtml() {
    const webview = this.panel.webview;

    const scriptUri = webview.asWebviewUri(
      vscode.Uri.joinPath(this.extensionUri, 'dist', 'webview', 'visualization.js')
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
  <title>ASP Visualization</title>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="${scriptUri}"></script>
</body>
</html>`;
  }

  public dispose() {
    VisualizationPanel.currentPanel = undefined;

    this.panel.dispose();

    while (this.disposables.length) {
      const d = this.disposables.pop();
      if (d) {
        d.dispose();
      }
    }
  }
}
