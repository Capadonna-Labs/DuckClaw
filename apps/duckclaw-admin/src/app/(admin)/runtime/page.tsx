'use client';

import { useEffect, useState } from 'react';
import { adminService } from '@/services/adminService';

export default function RuntimePage() {
  const [vaults, setVaults] = useState<{ path: string }[]>([]);
  const [vault, setVault] = useState('');
  const [chatId, setChatId] = useState('default');
  const [rows, setRows] = useState<{ key: string; value: string }[]>([]);
  const [newKey, setNewKey] = useState('');
  const [newVal, setNewVal] = useState('');

  useEffect(() => {
    adminService.listVaults().then((r) => {
      setVaults(r.vaults);
      if (r.vaults[0]) setVault(r.vaults[0].path);
    });
  }, []);

  const load = () => {
    if (!vault) return;
    adminService.getRuntimeConfig(vault, chatId).then((r) => setRows(r.rows ?? []));
  };

  useEffect(() => {
    load();
  }, [vault, chatId]);

  const save = async () => {
    await adminService.putRuntimeConfig({
      vault_path: vault,
      chat_id: chatId,
      key: newKey,
      value: newVal,
    });
    setNewKey('');
    setNewVal('');
    load();
  };

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-black dark:text-dark-text">Runtime (agent_config)</h1>
      <div className="flex flex-wrap gap-3">
        <select
          value={vault}
          onChange={(e) => setVault(e.target.value)}
          className="px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-surface text-sm font-mono"
        >
          {vaults.map((v) => (
            <option key={v.path} value={v.path}>
              {v.path}
            </option>
          ))}
        </select>
        <input
          value={chatId}
          onChange={(e) => setChatId(e.target.value)}
          className="px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-surface text-sm"
          placeholder="chat_id"
        />
      </div>
      <table className="w-full text-sm bg-white dark:bg-dark-surface rounded-2xl border dark:border-dark-border overflow-hidden">
        <thead className="bg-gov-gray-50 dark:bg-dark-bg">
          <tr>
            <th className="px-4 py-2 text-left">key</th>
            <th className="px-4 py-2 text-left">value</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className="border-t dark:border-dark-border">
              <td className="px-4 py-2 font-mono text-xs">{r.key}</td>
              <td className="px-4 py-2 font-mono text-xs truncate max-w-xl">{r.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <motionUpsertForm
        newKey={newKey}
        setNewKey={setNewKey}
        newVal={newVal}
        setNewVal={setNewVal}
        onSave={save}
      />
    </div>
  );
}

function motionUpsertForm({
  newKey,
  setNewKey,
  newVal,
  setNewVal,
  onSave,
}: {
  newKey: string;
  setNewKey: (v: string) => void;
  newVal: string;
  setNewVal: (v: string) => void;
  onSave: () => void;
}) {
  return (
    <div className="flex flex-wrap gap-2 max-w-3xl">
      <input
        value={newKey}
        onChange={(e) => setNewKey(e.target.value)}
        placeholder="key"
        className="flex-1 px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-surface font-mono text-sm"
      />
      <input
        value={newVal}
        onChange={(e) => setNewVal(e.target.value)}
        placeholder="value"
        className="flex-[2] px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-surface font-mono text-sm"
      />
      <button
        type="button"
        onClick={onSave}
        className="px-4 py-2 bg-gov-blue-700 text-white rounded-xl text-sm font-bold"
      >
        Upsert
      </button>
    </div>
  );
}
