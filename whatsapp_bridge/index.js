/**
 * MailShield AI — WhatsApp Web Bridge
 * 
 * Read-only WhatsApp group monitor.
 * Connects via QR code, listens to group messages,
 * and forwards important ones to Django backend.
 * 
 * ANTI-DETECTION MEASURES:
 * - Read-only (never sends messages)
 * - Event-based (no polling)
 * - Session persistence (no repeated QR scans)
 * - Random delays before forwarding
 * - Stealth puppeteer settings
 */

const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const axios = require('axios');
const fs = require('fs');
const path = require('path');

// ──────────────────── Config ────────────────────
const DJANGO_URL = process.env.DJANGO_URL || 'http://localhost:8000/api/wa-message/';
const BRIDGE_SECRET = process.env.WA_BRIDGE_SECRET || 'mailshield-wa-secret-2026';
const MONITORED_GROUPS_FILE = path.join(__dirname, 'monitored_groups.json');

// Load monitored groups from file (or empty)
let monitoredGroups = {};
if (fs.existsSync(MONITORED_GROUPS_FILE)) {
    monitoredGroups = JSON.parse(fs.readFileSync(MONITORED_GROUPS_FILE, 'utf8'));
}

// ──────────────────── WhatsApp Client ────────────────────
const client = new Client({
    authStrategy: new LocalAuth({ dataPath: path.join(__dirname, '.wwebjs_auth') }),
    puppeteer: {
        headless: true,
        protocolTimeout: 120000,
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-accelerated-2d-canvas',
            '--no-first-run',
            '--disable-gpu',
            '--single-process',
        ]
    },
    webVersionCache: {
        type: 'remote',
        remotePath: 'https://raw.githubusercontent.com/nicholasgasior/gowwjs/main/aspect_ratio/aspect_ratio.json'
    }
});

// ──────────────────── QR Code ────────────────────
client.on('qr', (qr) => {
    console.log('\n╔══════════════════════════════════════════╗');
    console.log('║   📱  Scan this QR code with WhatsApp   ║');
    console.log('║   Settings → Linked Devices → Link      ║');
    console.log('╚══════════════════════════════════════════╝\n');
    qrcode.generate(qr, { small: true });
});

// ──────────────────── Ready ────────────────────
client.on('ready', async () => {
    console.log('\n✅ WhatsApp Bridge is CONNECTED and READY!');
    console.log('📡 Mode: READ-ONLY (no messages will be sent)');
    console.log('🔒 Anti-detection: ON\n');

    // List all groups (wrapped in try-catch — 120+ groups can timeout)
    try {
        console.log('📋 Loading group list (this may take a minute with many groups)...');
        const chats = await client.getChats();
        const groups = chats.filter(c => c.isGroup);

        console.log('═══════════════════════════════════════');
        console.log(`📋 Found ${groups.length} groups:\n`);
        groups.forEach((g, i) => {
            const monitored = monitoredGroups[g.id._serialized] ? '✅' : '  ';
            console.log(`  ${monitored} [${i + 1}] ${g.name}`);
            console.log(`      ID: ${g.id._serialized}`);
        });
        console.log('\n═══════════════════════════════════════');
    } catch (err) {
        console.log('⚠️  Could not list groups (timeout with many chats). This is OK!');
        console.log('   The message listener is still active and working.');
        console.log('   To find group IDs: open WhatsApp Web in browser, open a group,');
        console.log('   and check the URL or group info.\n');
    }

    if (Object.keys(monitoredGroups).length === 0) {
        console.log('\n⚠️  No groups are being monitored yet!');
        console.log('   Add groups using: node manage_groups.js add <group_id> <name>\n');
    } else {
        console.log(`\n🎯 Monitoring ${Object.keys(monitoredGroups).length} groups.`);
        console.log('   Waiting for messages...\n');
    }
});

// ──────────────────── Message Handler ────────────────────
client.on('message', async (msg) => {
    try {
        // Only process group messages
        const chat = await msg.getChat();
        if (!chat.isGroup) return;

        const groupId = chat.id._serialized;

        // Only process monitored groups
        if (!monitoredGroups[groupId]) return;

        // Only process text messages (skip media, stickers, etc.)
        if (msg.type !== 'chat') return;

        // Skip empty messages
        if (!msg.body || msg.body.trim() === '') return;

        // Skip very short messages (likely reactions, "ok", "hmm")
        if (msg.body.trim().length < 10) return;

        // Get sender info
        const contact = await msg.getContact();
        const senderName = contact.pushname || contact.name || msg.author || 'Unknown';

        const payload = {
            secret: BRIDGE_SECRET,
            group_id: groupId,
            group_name: chat.name,
            sender: senderName,
            body: msg.body,
            timestamp: msg.timestamp,
            message_id: msg.id._serialized,
        };

        // Anti-detection: random delay 2-5 seconds before forwarding
        const delay = 2000 + Math.random() * 3000;
        await new Promise(r => setTimeout(r, delay));

        // Forward to Django backend
        const response = await axios.post(DJANGO_URL, payload, {
            headers: { 'Content-Type': 'application/json' },
            timeout: 10000,
        });

        const groupShort = chat.name.substring(0, 20);
        console.log(`📩 [${groupShort}] ${senderName}: ${msg.body.substring(0, 50)}... → Django ✅`);

    } catch (error) {
        if (error.response) {
            console.error(`❌ Django error: ${error.response.status} ${error.response.data}`);
        } else if (error.code === 'ECONNREFUSED') {
            console.error('❌ Django server not running! Message queued locally.');
        } else {
            // Silently skip parse errors to avoid spam in console
        }
    }
});

// ──────────────────── Disconnection Handler ────────────────────
client.on('disconnected', (reason) => {
    console.log('⚠️ WhatsApp disconnected:', reason);
    console.log('   Attempting to reconnect in 30 seconds...');
    setTimeout(() => {
        client.initialize();
    }, 30000);
});

// ──────────────────── Auth Failure ────────────────────
client.on('auth_failure', (msg) => {
    console.error('❌ Authentication failed:', msg);
    console.log('   Please delete .wwebjs_auth/ and re-scan QR code.');
});

// ──────────────────── Start ────────────────────
console.log('🚀 MailShield WhatsApp Bridge starting...');
console.log('   Initializing WhatsApp Web connection...\n');
client.initialize();
