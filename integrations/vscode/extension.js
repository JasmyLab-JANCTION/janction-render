// JANCTION Render の MCP サーバーを VS Code に登録するだけの拡張（10/21）。中身は https://render.janction.jp/mcp（OAuth で鍵を結ぶ）。
const vscode = require('vscode');

function activate(context) {
  context.subscriptions.push(vscode.lm.registerMcpServerDefinitionProvider('janction-render', {
    provideMcpServerDefinitions: async () => [
      new vscode.McpHttpServerDefinition('JANCTION Render', vscode.Uri.parse('https://render.janction.jp/mcp'), {}, '0.1.0'),
    ],
  }));
}

function deactivate() {}

module.exports = { activate, deactivate };
