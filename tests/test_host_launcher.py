"""DSH_MODULE_ROOT=/absolute/node_modules python3 -B -m unittest discover -s tests."""
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from host_launcher import FRAMEWORK, launch


JS = r'''
import assert from 'node:assert/strict';
import {existsSync, readFileSync, writeFileSync, symlinkSync} from 'node:fs';
import net from 'node:net';
const load = name => import(`/inputs/node_modules/@deepseek-ai/${name}/lib/index.js`);
const {Context} = await load('cordis');
const ctx = new Context();
for (const [name, config] of [
  ['dsh-session-projection', {}],
  ['dsh-sandbox-policy', {mode:'read-only', workspaceRoot:'/inputs/product'}],
  ['dsh-sandbox-local', {}], ['dsh-subprocess-local', {}],
  ['dsh-fs-sandbox', {cwd:'/inputs/product'}],
  ['dsh-bash-sandbox', {cwd:'/inputs/product', timeoutMs:5000}],
]) await ctx.plugin((await load(name)).default, config);
assert(ctx.fs && ctx.shell && ctx.subprocess && ctx.sandboxPolicy);
assert.equal(process.cwd(), '/inputs/product');
assert.equal(process.env.INHERITED_SECRET, undefined);
assert.equal(process.env.SSH_AUTH_SOCK, undefined);
for (const path of ['/home', '/run', '/etc', '/proc/1/root/home', '/inputs/product/escape']) {
  assert.equal(existsSync(path), false, path);
}
const policy = ctx.sandboxPolicy.resolve({mode:'danger-full-access'});
assert.equal(policy.mode, 'danger-full-access');
const read = async path => ctx.fs.readText(await ctx.fs.resolve(path));
assert(JSON.stringify(await read('/inputs/product/source.txt')).includes('product sentinel'));
assert(JSON.stringify(await read('/inputs/framework')).includes('repositorio'));
await ctx.fs.writeText(await ctx.fs.resolve('/state/fs.txt'), 'evidence', undefined, undefined, policy);
symlinkSync('/inputs/product', '/state/link');
const denials = [];
for (const path of ['/inputs/product/source.txt', '/inputs/product/new.txt',
  '/state/../inputs/product/source.txt', '/state/link/source.txt', '/inputs/framework']) {
  await assert.rejects(async () => ctx.fs.writeText(await ctx.fs.resolve(path), 'forbidden', undefined, undefined, policy), error => {
    assert(/read-only|EROFS|permission denied|EACCES/i.test(String(error)), String(error));
    denials.push(String(error).slice(0, 180));
    return true;
  });
}
const run = command => ctx.shell.run(ctx.shell.resolve({command, sandboxPolicy:policy}));
const success = await run('test "$PWD" = /inputs/product && printf bash-evidence > /state/bash.txt && /bin/sh -c "printf child-evidence"');
assert.equal(success.exitCode, 0, JSON.stringify(success));
assert(success.stdout.text.includes('child-evidence'));
const denied = await run('/bin/sh -c "printf forbidden > /inputs/product/source.txt"');
assert.notEqual(denied.exitCode, 0);
assert(/read-only|permission denied/i.test(denied.stderr.text), JSON.stringify(denied));
assert.equal(readFileSync('/inputs/product/source.txt', 'utf8'), 'product sentinel\n');
await assert.rejects(new Promise((resolve, reject) => {
  const client = net.connect({host:'127.0.0.1', port:Number(process.argv[2])});
  client.once('connect', () => { client.destroy(); resolve(); });
  client.once('error', reject);
}));
writeFileSync('/state/checked.json', JSON.stringify({services:true, fullHost:false,
  privateEnvironment:true, hostNetworkDenied:true, denials, descendantDenied:true}));
console.log('Installed DSH services: PASS; full Host: not tested here');
'''


class HostLauncherTest(unittest.TestCase):
    def test_real_services_and_fail_closed(self):
        runtime = os.environ.get('DSH_MODULE_ROOT')
        if not runtime:
            self.skipTest('Set DSH_MODULE_ROOT to installed runtime; no installation/fallback')
        root = Path(tempfile.mkdtemp(prefix='host-regression-', dir='/tmp'))
        print(f'Host regression evidence: {root}', flush=True)
        product, state_parent = root / 'product', root / 'runs'
        product.mkdir()
        state_parent.mkdir(mode=0o700)
        (product / 'source.txt').write_text('product sentinel\n')
        (root / 'private-credential').write_text('synthetic secret')
        (product / 'escape').symlink_to(root / 'private-credential')
        check = root / 'check.mjs'
        check.write_text(JS)
        reads = {'node_modules': runtime, 'product': product, 'framework': FRAMEWORK / 'AGENTS.md', 'check': check}
        options = dict(reads=reads, state_parent=state_parent, cwd='/inputs/product')
        with socket.socket() as server:
            server.bind(('127.0.0.1', 0))
            server.listen()
            state, code = launch(**options, argv=['/usr/bin/node', '/inputs/check', str(server.getsockname()[1])])
        self.assertEqual(code, 0, (state / 'stderr.log').read_text()[-3000:])
        self.assertEqual((product / 'source.txt').read_text(), 'product sentinel\n')
        self.assertEqual((state / 'fs.txt').read_text(), 'evidence')
        self.assertEqual((state / 'bash.txt').read_text(), 'bash-evidence')
        self.assertTrue((state / 'checked.json').is_file())
        second, code = launch(**options, argv=['/bin/sh', '-c', 'test ! -e /state/fs.txt && test ! -e /state/checked.json'])
        self.assertEqual(code, 0)
        self.assertNotEqual(state, second)
        self.assertEqual(second.stat().st_mode & 0o777, 0o700)
        _, code = launch(**options, argv=['/missing-executable'])
        self.assertNotEqual(code, 0)
        for changes in ({'state_parent': FRAMEWORK}, {'cwd': '/tmp'},
                        {'reads': {'private': Path.home()}}, {'reads': {'bad/name': product}},
                        {'reads': {'overlap': root}}, {'reads': {'link': product / 'escape'}}):
            with self.assertRaises(ValueError):
                launch(**(options | changes), argv=['/bin/true'])
        with socket.socket(socket.AF_UNIX) as unix:
            unix.bind(str(product / 'host.sock'))
            with self.assertRaises(ValueError):
                launch(**options, argv=['/bin/true'])


if __name__ == '__main__':
    unittest.main()
