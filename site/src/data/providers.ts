/* The four day-one adapters (providers/factory.py, config.py). Each one is
   written straight against the provider's HTTP API with httpx — no vendor SDK. */
export interface Provider {
    name: string;
    id: string;
    env: string;
    model: string;
    note: string;
}

export const providers: readonly Provider[] = [
    {
        name: 'Anthropic',
        id: 'anthropic',
        env: 'ANTHROPIC_API_KEY',
        model: 'claude-opus-5',
        note: 'the strongest hunter on our bench',
    },
    {
        name: 'OpenAI',
        id: 'openai',
        env: 'OPENAI_API_KEY',
        model: 'gpt-6-astra',
        note: 'streaming and tool use, same schema',
    },
    {
        name: 'Google Gemini',
        id: 'gemini',
        env: 'GEMINI_API_KEY',
        model: 'gemini-3.8-flash',
        note: 'the cheapest cloud run',
    },
    {
        name: 'Ollama',
        id: 'ollama',
        env: 'OLLAMA_HOST (no key)',
        model: 'qwen3.5:9b',
        note: 'fully offline · 32K context · qwen3.6:35b-a3b if you have ~23 GB',
    },
];

export const limits = [
    { value: '20', unit: 'rounds', what: 'reasoning budget per scan, set with --budget' },
    { value: '$5.00', unit: 'cap', what: 'hard cost ceiling, enforced by budget-quartermaster' },
    { value: '5', unit: 'at once', what: 'agents running concurrently' },
] as const;
