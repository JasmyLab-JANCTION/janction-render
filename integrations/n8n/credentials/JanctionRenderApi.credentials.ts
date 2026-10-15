import type { IAuthenticateGeneric, ICredentialTestRequest, ICredentialType, Icon, INodeProperties } from 'n8n-workflow';

export class JanctionRenderApi implements ICredentialType {
	name = 'janctionRenderApi';
	displayName = 'JANCTION Render API';
	icon: Icon = { light: 'file:janction.svg', dark: 'file:janction.dark.svg' };
	documentationUrl = 'https://github.com/JasmyLab-JANCTION/janction-render/tree/main/integrations/n8n';
	properties: INodeProperties[] = [
		{
			displayName: 'API Key',
			name: 'apiKey',
			type: 'string',
			typeOptions: { password: true },
			default: '',
			description: 'A key that starts with jr_. Create one at https://render.janction.jp/start (free GPU time to start).',
		},
	];
	authenticate: IAuthenticateGeneric = {
		type: 'generic',
		properties: { headers: { 'X-API-Key': '={{$credentials.apiKey}}' } },
	};
	test: ICredentialTestRequest = {
		request: { baseURL: 'https://render.janction.jp', url: '/v1/me?src=n8n' },
	};
}
