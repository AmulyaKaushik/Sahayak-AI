import { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { NoticeCard } from '@/components/notice-card';
import { colors } from '@/constants/colors';
import {
  getProfile,
  getProfileSchema,
  type ProfileFieldSpec,
  type ProfileValue,
} from '@/services/api';
import { optionLabel } from '@/utils/labels';

// The profile form used by both Onboarding (first login) and the Profile
// screen. Which fields it shows comes from GET /api/v1/profile/schema, so a
// field that a new scheme needs appears here without an app update.

// ---- Loading the schema + current values ------------------------------------

export function useProfileData() {
  const [schema, setSchema] = useState<ProfileFieldSpec[] | null>(null);
  const [fields, setFields] = useState<Record<string, ProfileValue>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Bumped on every successful reload; use it as the form's `key` so the form
  // remounts with the fresh values.
  const [version, setVersion] = useState(0);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, p] = await Promise.all([getProfileSchema(), getProfile()]);
      setSchema(s);
      setFields(p.fields);
      setVersion((v) => v + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  // setFields: store the server's answer after a save without remounting.
  return { schema, fields, setFields, version, loading, error, reload };
}

// ---- Form -------------------------------------------------------------------

// What each input holds while editing. Numbers and free text are kept as the
// typed string; booleans/selects as the value or null (= not answered).
type Draft = string | boolean | string[] | null;

// A multiselect with no fixed options (e.g. "existing products") is typed as a
// comma-separated list.
const isFreeList = (spec: ProfileFieldSpec) => spec.type === 'multiselect' && spec.options.length === 0;

function toDraft(spec: ProfileFieldSpec, value: ProfileValue | undefined): Draft {
  if (value === null || value === undefined) {
    if (spec.type === 'boolean' || spec.type === 'select') return null;
    if (spec.type === 'multiselect' && !isFreeList(spec)) return [];
    return '';
  }
  if (spec.type === 'number') return String(value);
  if (spec.type === 'multiselect') {
    const list = Array.isArray(value) ? value : [String(value)];
    return isFreeList(spec) ? list.join(', ') : list;
  }
  if (spec.type === 'boolean') return value === true;
  return String(value);
}

// Draft -> value for the API. Throws a readable message for a bad number.
function fromDraft(spec: ProfileFieldSpec, draft: Draft): ProfileValue {
  if (spec.type === 'number') {
    const text = String(draft ?? '').trim().replace(/,/g, '');
    if (!text) return null;
    const n = Number(text);
    if (!Number.isFinite(n) || n < 0) throw new Error('Enter a number (0 or more)');
    return n;
  }
  if (spec.type === 'text') return String(draft ?? '').trim() || null;
  if (isFreeList(spec)) {
    const list = String(draft ?? '')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    return list.length ? list : null;
  }
  if (spec.type === 'multiselect') return Array.isArray(draft) && draft.length ? draft : null;
  return draft as ProfileValue; // boolean | select: already the value or null
}

const same = (a: ProfileValue | undefined, b: ProfileValue | undefined) =>
  JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

export function ProfileForm({
  schema,
  initial,
  submitLabel,
  onSubmit,
  secondaryAction,
  intro,
}: {
  schema: ProfileFieldSpec[];
  initial: Record<string, ProfileValue>;
  submitLabel: string;
  // Receives only the fields that changed. Throw to show an error.
  onSubmit: (updates: Record<string, ProfileValue>) => Promise<void>;
  secondaryAction?: { label: string; onPress: () => Promise<void> | void };
  intro?: string;
}) {
  // Initialised once. To show new server data (e.g. a fact the chat saved),
  // the screen remounts the form by changing its `key`.
  const [drafts, setDrafts] = useState<Record<string, Draft>>(() =>
    Object.fromEntries(schema.map((s) => [s.field, toDraft(s, initial[s.field])])),
  );
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<'submit' | 'secondary' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const setDraft = (field: string, value: Draft) => {
    setDrafts((d) => ({ ...d, [field]: value }));
    setFieldErrors((e) => ({ ...e, [field]: '' }));
    setSaved(false);
  };

  async function submit() {
    const updates: Record<string, ProfileValue> = {};
    const errors: Record<string, string> = {};
    for (const spec of schema) {
      try {
        const value = fromDraft(spec, drafts[spec.field]);
        if (!same(value, initial[spec.field])) updates[spec.field] = value;
      } catch (e) {
        errors[spec.field] = e instanceof Error ? e.message : String(e);
      }
    }
    setFieldErrors(errors);
    if (Object.values(errors).some(Boolean)) {
      setError('Please fix the highlighted fields.');
      return;
    }
    setBusy('submit');
    setError(null);
    try {
      await onSubmit(updates);
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  async function secondary() {
    if (!secondaryAction) return;
    setBusy('secondary');
    setError(null);
    try {
      await secondaryAction.onPress();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 100 : 0}>
      <ScrollView
        style={styles.flex}
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled">
        {intro && <Text style={styles.intro}>{intro}</Text>}

        {schema.map((spec) => (
          <View key={spec.field} style={styles.field}>
            <Text style={styles.label}>
              {spec.label}
              {spec.required && <Text style={styles.required}> *</Text>}
            </Text>
            <FieldInput spec={spec} value={drafts[spec.field]} onChange={(v) => setDraft(spec.field, v)} />
            {!!fieldErrors[spec.field] && <Text style={styles.fieldError}>{fieldErrors[spec.field]}</Text>}
          </View>
        ))}
        <Text style={styles.hint}>
          * Needed by most loans and schemes. Everything is optional: you can also tell Sahayak these
          details by voice.
        </Text>

        {error && <NoticeCard tone="danger" message={error} />}
        {saved && !error && <Text style={styles.saved}>Saved.</Text>}

        <Pressable
          onPress={submit}
          disabled={busy !== null}
          style={({ pressed }) => [styles.primary, (pressed || busy) && styles.dimmed]}>
          {busy === 'submit' ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.primaryText}>{submitLabel}</Text>
          )}
        </Pressable>
        {secondaryAction && (
          <Pressable onPress={secondary} disabled={busy !== null} style={styles.secondary}>
            {busy === 'secondary' ? (
              <ActivityIndicator color={colors.primary} />
            ) : (
              <Text style={styles.secondaryText}>{secondaryAction.label}</Text>
            )}
          </Pressable>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function FieldInput({
  spec,
  value,
  onChange,
}: {
  spec: ProfileFieldSpec;
  value: Draft;
  onChange: (value: Draft) => void;
}) {
  if (spec.type === 'boolean') {
    return (
      <Choices
        options={[
          { key: 'yes', label: 'Yes', selected: value === true, onPress: () => onChange(value === true ? null : true) },
          { key: 'no', label: 'No', selected: value === false, onPress: () => onChange(value === false ? null : false) },
        ]}
      />
    );
  }
  if (spec.type === 'select') {
    return (
      <Choices
        options={spec.options.map((o) => ({
          key: o,
          label: optionLabel(o),
          selected: value === o,
          onPress: () => onChange(value === o ? null : o), // tap again to clear
        }))}
      />
    );
  }
  if (spec.type === 'multiselect' && !isFreeList(spec)) {
    const list = Array.isArray(value) ? value : [];
    return (
      <Choices
        options={spec.options.map((o) => ({
          key: o,
          label: optionLabel(o),
          selected: list.includes(o),
          onPress: () => onChange(list.includes(o) ? list.filter((x) => x !== o) : [...list, o]),
        }))}
      />
    );
  }
  return (
    <TextInput
      value={typeof value === 'string' ? value : ''}
      onChangeText={onChange}
      keyboardType={spec.type === 'number' ? 'decimal-pad' : 'default'}
      placeholder={isFreeList(spec) ? 'e.g. savings account, debit card' : undefined}
      placeholderTextColor={colors.textFaint}
      style={styles.input}
      accessibilityLabel={spec.label}
    />
  );
}

function Choices({
  options,
}: {
  options: { key: string; label: string; selected: boolean; onPress: () => void }[];
}) {
  return (
    <View style={styles.choices}>
      {options.map((o) => (
        <Pressable
          key={o.key}
          onPress={o.onPress}
          accessibilityRole="button"
          accessibilityState={{ selected: o.selected }}
          style={[styles.choice, o.selected && styles.choiceSelected]}>
          <Text style={[styles.choiceText, o.selected && styles.choiceTextSelected]}>{o.label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.background },
  content: { padding: 20, paddingBottom: 48 },
  intro: { fontSize: 15, color: colors.textMuted, lineHeight: 22, marginBottom: 8 },
  field: { marginTop: 18 },
  label: { fontSize: 16, fontWeight: '600', color: colors.text, marginBottom: 8 },
  required: { color: colors.danger },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 12,
    fontSize: 17,
    color: colors.text,
    backgroundColor: colors.surface,
  },
  fieldError: { color: colors.danger, fontSize: 13, marginTop: 4 },
  choices: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  choice: {
    paddingHorizontal: 14,
    paddingVertical: 9,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  choiceSelected: { backgroundColor: colors.primary, borderColor: colors.primary },
  choiceText: { fontSize: 15, color: colors.text },
  choiceTextSelected: { color: '#fff', fontWeight: '600' },
  hint: { fontSize: 13, color: colors.textFaint, marginTop: 20, marginBottom: 12, lineHeight: 18 },
  saved: { color: colors.success, fontSize: 15, fontWeight: '600', textAlign: 'center', marginBottom: 8 },
  primary: {
    backgroundColor: colors.primary,
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 8,
  },
  primaryText: { color: '#fff', fontSize: 17, fontWeight: '700' },
  secondary: { paddingVertical: 14, alignItems: 'center', marginTop: 4 },
  secondaryText: { color: colors.primary, fontSize: 16, fontWeight: '600' },
  dimmed: { opacity: 0.7 },
});
