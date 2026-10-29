import { describe, expect, it } from 'vitest';
import { ageLabel, botDraftOf, parseJsonObject, worldDraftOf, type World, type WorldBot } from './worldsTypes';

describe('parseJsonObject', () => {
  it('accepts an object, an empty text and rejects everything else with a Spanish message', () => {
    expect(parseJsonObject('{"edition": "java", "plugins": ["geyser"]}')).toEqual({ value: { edition: 'java', plugins: ['geyser'] } });
    expect(parseJsonObject('   ')).toEqual({ value: {} });
    for (const bad of ['[1, 2]', '"text"', '42', 'null']) {
      expect('error' in parseJsonObject(bad)).toBe(true);
    }
    const broken = parseJsonObject('{"a": ');
    expect('error' in broken && broken.error).toMatch(/JSON inválido/);
  });
});

describe('drafts', () => {
  const world = { id: 'w', name: 'Casa', kind: 'minecraft', host: '10.0.0.5', port: 25565, config: { edition: 'java' }, enabled: false, bots: [] } as World;
  const bot = { id: 'b', world_id: 'w', name: 'Capadonna', worker_id: 'npc', settings: { model: 'm' }, enabled: true } as WorldBot;

  it('round-trips an existing world and bot into form text', () => {
    const d = worldDraftOf(world);
    expect([d.name, d.kind, d.host, d.port, d.enabled]).toEqual(['Casa', 'minecraft', '10.0.0.5', '25565', false]);
    expect(JSON.parse(d.config)).toEqual({ edition: 'java' });
    expect(JSON.parse(botDraftOf(bot).settings)).toEqual({ model: 'm' });
  });

  it('starts a new world generic, enabled and with an empty config', () => {
    const d = worldDraftOf();
    expect([d.kind, d.port, d.enabled, d.config]).toEqual(['generic', '', true, '{}']);
  });
});

describe('ageLabel', () => {
  it('speaks in seconds, minutes and hours', () => {
    expect(ageLabel(null)).toBe('sin reportes');
    expect(ageLabel(12)).toBe('hace 12s');
    expect(ageLabel(150)).toBe('hace 2 min');
    expect(ageLabel(7300)).toBe('hace 2 h');
  });
});
