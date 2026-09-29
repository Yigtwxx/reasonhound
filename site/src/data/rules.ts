/* The hard constraints from CLAUDE.md, as the page tells them. Each is a thing
   the tool will never do, whatever the code in front of it says. */
import type { IconName } from '../components/sketch/SketchIcon.astro';

export interface Rule {
    id: string;
    icon: IconName;
    title: string;
    body: string;
    margin: string;
}

export const rules: readonly Rule[] = [
    {
        id: 'redact',
        icon: 'key',
        title: 'Never sends a secret to a model.',
        body: 'egress-redactor runs before anything leaves your machine: private keys, JWTs, cloud and API keys, bearer tokens, URL credentials, and anything with the *entropy* of a secret become a labelled placeholder. It cannot be switched off.',
        margin: 'The model sees the shape of the leak, never the leak.',
    },
    {
        id: 'fence',
        icon: 'doc',
        title: 'Never takes orders from the code it reads.',
        body: 'Every file reaches the model inside *untrusted-data fences*, and fence markers planted in the code are neutralised. A comment that says "ignore previous instructions" is a *finding*, not an instruction.',
        margin: 'Not even an inline “reasonhound: ignore” — an attacker could plant one.',
    },
    {
        id: 'allowlist',
        icon: 'lock',
        title: 'Never hands an agent a tool it was not given.',
        body: 'Each agent has an allowlist; a call outside it fails with *ToolDenied*. File tools are read-only and stop at the project root, so there is *no path from a file to the network*.',
        margin: 'The nose that reads your code never holds the leash to the internet.',
    },
    {
        id: 'schema',
        icon: 'window',
        title: 'Never answers in free text.',
        body: 'An agent can only finish through *submit_result*, and its answer must pass a strict schema. No shell command, no prose to be executed, no surprise field: *extra fields are rejected*.',
        margin: 'It fills in the form, or it is not heard.',
    },
    {
        id: 'egress',
        icon: 'globe',
        title: 'Never probes outside the target.',
        body: 'The dynamic phase runs in an isolated Docker network with egress closed. The policy *fails closed*, allows HTTP(S) to the target alone, and escape-watchdog kills the scan on the first out-of-scope request.',
        margin: 'Off the leash is off the case.',
    },
    {
        id: 'consent',
        icon: 'spark',
        title: 'Never hunts without your word.',
        body: 'Every run asks you to confirm you own the system or are *explicitly authorized* to test it — every time, never saved. Destructive checks need *--aggressive* and a second, interactive yes that no flag can skip, not even -y.',
        margin: 'Asked each run. Remembered never.',
    },
    {
        id: 'memory',
        icon: 'search',
        title: 'Never lets its memory leave the machine.',
        body: 'What a scan learns lives in *Reasonhound/.memory/*, embedded by a *local* Ollama model, written only from verified outcomes and forgotten the moment a file’s hash changes. It is gitignored from the first run.',
        margin: 'It remembers the trail, not your code.',
    },
];
