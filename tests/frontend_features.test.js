const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const htmlPath = path.join(__dirname, '..', 'app', 'static', 'index.html');
const html = fs.readFileSync(htmlPath, 'utf8');

function loadReminderBucket() {
  const match = html.match(/function\s+reminderBucket\s*\(\s*timestamp\s*,\s*now\s*=\s*new Date\(\)\s*\)\s*\{[\s\S]*?\}/);
  assert.ok(match, 'reminderBucket(timestamp, now) must exist for reminder bucketing');
  return new Function(match[0] + '; return reminderBucket;')();
}

test('reminder bucket treats a follow-up before the current time as overdue', () => {
  const bucket = loadReminderBucket();
  const now = new Date(2026, 9, 27, 12, 0, 0);
  const earlierToday = new Date(2026, 9, 27, 10, 0, 0);
  assert.equal(bucket(earlierToday.toISOString(), now), 'overdue');
});

test('reminder bucket treats a future time later today as due today', () => {
  const bucket = loadReminderBucket();
  const now = new Date(2026, 9, 27, 12, 0, 0);
  const laterToday = new Date(2026, 9, 27, 17, 30, 0);
  assert.equal(bucket(laterToday.toISOString(), now), 'today');
});

test('reminder bucket treats a follow-up tomorrow as upcoming', () => {
  const bucket = loadReminderBucket();
  const now = new Date(2026, 9, 27, 23, 59, 0);
  const tomorrow = new Date(2026, 9, 28, 0, 1, 0);
  assert.equal(bucket(tomorrow.toISOString(), now), 'upcoming');
});

test('reminder bucket uses local calendar boundaries across midnight', () => {
  const bucket = loadReminderBucket();
  const beforeMidnight = new Date(2026, 9, 27, 23, 59, 0);
  const afterMidnight = new Date(2026, 9, 28, 0, 1, 0);
  assert.equal(bucket(afterMidnight.toISOString(), beforeMidnight), 'upcoming');
  assert.equal(bucket(beforeMidnight.toISOString(), new Date(2026, 9, 27, 23, 58, 0)), 'today');
});

test('reminder bucket rejects malformed timestamps without throwing', () => {
  const bucket = loadReminderBucket();
  assert.equal(bucket('not-a-date', new Date(2026, 9, 27, 12, 0, 0)), 'invalid');
});

function loadFutureTimestampValidator() {
  const match = html.match(/function\s+isFutureTimestamp\s*\(\s*value\s*,\s*now\s*=\s*Date\.now\(\)\s*\)\s*\{[\s\S]*?\}/);
  assert.ok(match, 'isFutureTimestamp(value, now) must validate reminder rescheduling');
  return new Function(match[0] + '; return isFutureTimestamp;')();
}

test('future timestamp validator accepts a strictly future follow-up', () => {
  const validate = loadFutureTimestampValidator();
  assert.equal(validate('2026-10-27T13:00:00.000Z', Date.parse('2026-10-27T12:00:00.000Z')), true);
});

test('future timestamp validator rejects equal, past, and invalid times', () => {
  const validate = loadFutureTimestampValidator();
  const now = Date.parse('2026-10-27T12:00:00.000Z');
  assert.equal(validate('2026-10-27T12:00:00.000Z', now), false);
  assert.equal(validate('2026-10-27T11:59:59.000Z', now), false);
  assert.equal(validate('invalid-date', now), false);
});

function loadActiveReminderStatusFilter() {
  const match = html.match(/function\s+isActiveReminderStatus\s*\(\s*status\s*\)\s*\{[\s\S]*?\}/);
  assert.ok(match, 'isActiveReminderStatus(status) must exclude closed leads from reminders');
  return new Function(match[0] + '; return isActiveReminderStatus;')();
}

test('reminder eligibility excludes won and lost leads but keeps active stages', () => {
  const eligible = loadActiveReminderStatusFilter();
  assert.equal(eligible('qualified'), true);
  assert.equal(eligible('nurture'), true);
  assert.equal(eligible('won'), false);
  assert.equal(eligible('lost'), false);
});

function loadReportDateFieldValue() {
  const match = html.match(/function\s+reportDateFieldValue\s*\(\s*d\s*\)\s*\{[\s\S]*?\}/);
  assert.ok(match, 'reportDateFieldValue(date) must format Asia/Kolkata calendar dates');
  return new Function(match[0] + '; return reportDateFieldValue;')();
}

test('report date fields use Asia/Kolkata calendar date rather than browser UTC date', () => {
  const format = loadReportDateFieldValue();
  assert.equal(format(new Date('2026-10-26T18:45:00.000Z')), '2026-10-27');
  assert.equal(format(new Date('2026-10-27T18:29:59.000Z')), '2026-10-27');
  assert.equal(format(new Date('2026-10-27T18:30:00.000Z')), '2026-10-28');
});


test('employee creation controls are restricted to administrator role in the UI', () => {
  assert.match(html, /addEmployeeBtn\.classList\.toggle\('hidden',!currentUser\|\|currentUser\.role!=='admin'\)/);
  assert.match(html, /Only organization admins can create employees\. Current role:/);
});
