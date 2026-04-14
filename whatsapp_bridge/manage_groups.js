/**
 * Manage monitored WhatsApp groups
 * Usage:
 *   node manage_groups.js list              — Show all monitored groups
 *   node manage_groups.js add <id> <name>   — Add a group to monitor
 *   node manage_groups.js remove <id>       — Remove a group
 */

const fs = require('fs');
const path = require('path');

const FILE = path.join(__dirname, 'monitored_groups.json');

let groups = {};
if (fs.existsSync(FILE)) {
    groups = JSON.parse(fs.readFileSync(FILE, 'utf8'));
}

const [,, cmd, id, ...nameParts] = process.argv;
const name = nameParts.join(' ');

switch (cmd) {
    case 'list':
        console.log('\n📋 Monitored Groups:\n');
        const entries = Object.entries(groups);
        if (entries.length === 0) {
            console.log('   No groups monitored yet.');
        } else {
            entries.forEach(([gid, gname], i) => {
                console.log(`  [${i + 1}] ${gname}`);
                console.log(`      ID: ${gid}`);
            });
        }
        console.log('');
        break;

    case 'add':
        if (!id || !name) {
            console.log('Usage: node manage_groups.js add <group_id> <group_name>');
            process.exit(1);
        }
        groups[id] = name;
        fs.writeFileSync(FILE, JSON.stringify(groups, null, 2));
        console.log(`✅ Added: ${name} (${id})`);
        break;

    case 'remove':
        if (!id) {
            console.log('Usage: node manage_groups.js remove <group_id>');
            process.exit(1);
        }
        if (groups[id]) {
            const removed = groups[id];
            delete groups[id];
            fs.writeFileSync(FILE, JSON.stringify(groups, null, 2));
            console.log(`🗑️  Removed: ${removed} (${id})`);
        } else {
            console.log(`❌ Group ${id} not found.`);
        }
        break;

    default:
        console.log('Usage:');
        console.log('  node manage_groups.js list');
        console.log('  node manage_groups.js add <group_id> <group_name>');
        console.log('  node manage_groups.js remove <group_id>');
}
