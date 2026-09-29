/* The subagent library (docs/DESIGN.md §4): 35 agents in 7 groups. The
   lead-strategist picks a subset per run; each agent can call only the tools
   in its own kit, and finishes only through `submit_result`. */
export interface Agent {
    name: string;
    role: string;
    kit: string;
}

export interface Pack {
    id: string;
    title: string;
    note: string;
    agents: readonly Agent[];
}

export const packs: readonly Pack[] = [
    {
        id: 'lead',
        title: 'The lead',
        note: 'Plans the hunt, picks the pack, owns the budget.',
        agents: [
            {
                name: 'lead-strategist',
                role: 'plans, dispatches, dedups, keeps the status board',
                kit: 'task-dispatch · budget-ledger · findings-store',
            },
        ],
    },
    {
        id: 'recon',
        title: 'Recon',
        note: 'Maps the ground before anyone hunts.',
        agents: [
            {
                name: 'framework-fingerprinter',
                role: 'language, framework, versions',
                kit: 'fs.read · deps.manifest',
            },
            {
                name: 'attack-surface-mapper',
                role: 'routes, endpoints, input points',
                kit: 'fs.grep · ast.parse',
            },
            {
                name: 'auth-surface-scout',
                role: 'session and authz code paths',
                kit: 'fs.grep · ast.parse',
            },
            {
                name: 'data-flow-tracer',
                role: 'taint: source → sink',
                kit: 'ast.parse · dataflow.trace',
            },
            {
                name: 'trust-boundary-cartographer',
                role: 'where untrusted data crosses over',
                kit: 'ast.parse · fs.grep',
            },
        ],
    },
    {
        id: 'hunters',
        title: 'Hunters',
        note: 'One nose per vulnerability class.',
        agents: [
            {
                name: 'injection-hunter',
                role: 'SQL, NoSQL, OS, LDAP injection',
                kit: 'ast.parse · dataflow.trace',
            },
            { name: 'xss-analyst', role: 'reflected and stored XSS', kit: 'ast.parse · fs.grep' },
            {
                name: 'ssrf-hunter',
                role: 'server-side request forgery',
                kit: 'dataflow.trace · fs.grep',
            },
            {
                name: 'deserialization-analyst',
                role: 'unsafe deserialization',
                kit: 'ast.parse · fs.grep',
            },
            { name: 'path-traversal-hunter', role: 'traversal, LFI, RFI', kit: 'dataflow.trace' },
            {
                name: 'ssti-hunter',
                role: 'server-side template injection',
                kit: 'ast.parse · fs.grep',
            },
            {
                name: 'auth-logic-breaker',
                role: 'broken authz, IDOR, escalation',
                kit: 'ast.parse · fs.grep',
            },
            {
                name: 'business-logic-adversary',
                role: 'workflow bypass, price tampering',
                kit: 'ast.parse · dataflow.trace',
            },
            { name: 'race-condition-theorist', role: 'TOCTOU and races', kit: 'ast.parse' },
            {
                name: 'crypto-misuse-auditor',
                role: 'weak crypto, JWT alg confusion',
                kit: 'fs.grep · ast.parse',
            },
            {
                name: 'misconfig-auditor',
                role: 'debug endpoints, CORS, exposed config',
                kit: 'fs.read · fs.grep',
            },
            { name: 'file-upload-analyst', role: 'unrestricted upload', kit: 'ast.parse' },
        ],
    },
    {
        id: 'frontend',
        title: 'Frontend',
        note: 'What ships to the browser, read like source.',
        agents: [
            {
                name: 'bundle-archaeologist',
                role: 'source maps, hidden endpoints',
                kit: 'sourcemap.unpack · entropy.scan',
            },
            {
                name: 'dom-xss-hunter',
                role: 'client-side sources and sinks',
                kit: 'ast.parse (js)',
            },
            {
                name: 'browser-detonator',
                role: 'headless DOM XSS, postMessage, prototype pollution',
                kit: 'browser.headless (egress-locked)',
            },
            {
                name: 'supply-chain-inspector',
                role: 'vulnerable deps, typosquats, install scripts',
                kit: 'deps.audit · lockfile.parse',
            },
            {
                name: 'framework-specialist',
                role: 'server actions, NEXT_PUBLIC_ leaks',
                kit: 'ast.parse · fs.grep',
            },
            {
                name: 'client-secret-forager',
                role: 'keys and tokens shipped to the client',
                kit: 'fs.grep · entropy.scan',
            },
        ],
    },
    {
        id: 'dynamic',
        title: 'Dynamic',
        note: 'Egress-locked. Harmless by default.',
        agents: [
            {
                name: 'env-conductor',
                role: 'brings the app up, or attaches with --target',
                kit: 'docker.up · net.egress_guard',
            },
            {
                name: 'harmless-prober',
                role: 'timing, boolean and reflection probes',
                kit: 'http.probe (egress-locked)',
            },
            {
                name: 'exploit-smith',
                role: 'PoC — only with --aggressive and a typed yes',
                kit: 'http.probe · audit.log',
            },
            {
                name: 'escape-watchdog',
                role: 'kills the scan on any out-of-scope request',
                kit: 'net.egress_guard · kill.signal',
            },
        ],
    },
    {
        id: 'verify',
        title: 'Verification',
        note: 'Two votes and a judge.',
        agents: [
            {
                name: 'red-verifier',
                role: 'tries to prove it',
                kit: 'fs.read · http.probe · ast.parse',
            },
            { name: 'blue-refuter', role: 'tries to disprove it', kit: 'fs.read · ast.parse' },
            { name: 'arbiter', role: 'confirmed, suspected or rejected', kit: 'findings-store' },
            {
                name: 'reproducer',
                role: 'minimal PoC for what was confirmed',
                kit: 'http.probe · capture',
            },
        ],
    },
    {
        id: 'support',
        title: 'Support',
        note: 'The leash, the ledger and the scribe.',
        agents: [
            {
                name: 'egress-redactor',
                role: 'masks secrets before anything leaves',
                kit: 'redact · entropy.scan',
            },
            {
                name: 'injection-warden',
                role: 'fences untrusted file content',
                kit: 'fence · anomaly.detect',
            },
            { name: 'severity-scorer', role: 'CVSS × confidence, dedup', kit: 'findings-store' },
            { name: 'report-scribe', role: 'writes the Reasonhound/ folder', kit: 'report.write' },
            {
                name: 'budget-quartermaster',
                role: 'hard caps on tokens and dollars',
                kit: 'budget-ledger',
            },
            {
                name: 'status-broadcaster',
                role: 'drives the live monitor, handles stop',
                kit: 'status-board',
            },
        ],
    },
];

export const agentCount = packs.reduce((n, p) => n + p.agents.length, 0);
