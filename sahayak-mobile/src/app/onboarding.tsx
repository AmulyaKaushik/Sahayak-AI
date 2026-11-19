import { useEffect } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { NoticeCard } from '@/components/notice-card';
import { ProfileForm, useProfileData } from '@/components/profile-form';
import { colors } from '@/constants/colors';
import { updateProfile } from '@/services/api';
import { useAuth } from '@/store/auth';

// Route "/onboarding": shown once after registering, until the profile is
// saved or skipped. Saving (even an empty "Skip") marks the profile as
// completed on the server, and the root layout then switches to the chat.
export default function OnboardingScreen() {
  const { schema, fields, version, loading, error, reload } = useProfileData();
  const markProfileCompleted = useAuth((s) => s.markProfileCompleted);

  useEffect(() => {
    reload();
  }, [reload]);

  async function save(updates: Parameters<typeof updateProfile>[0]) {
    await updateProfile(updates);
    await markProfileCompleted();
  }

  if (!schema) {
    return (
      <View style={styles.center}>
        {loading ? (
          <ActivityIndicator size="large" color={colors.primary} />
        ) : (
          <NoticeCard
            tone="danger"
            message={error ?? 'Could not load the form.'}
            actions={[{ label: 'Retry', onPress: reload }]}
          />
        )}
      </View>
    );
  }

  return (
    <ProfileForm
      key={version}
      schema={schema}
      initial={fields}
      intro="A few details help Sahayak tell you which loans and schemes you qualify for. Fill in what you're comfortable with, or skip and tell Sahayak later by voice."
      submitLabel="Save and continue"
      onSubmit={save}
      secondaryAction={{ label: 'Skip for now', onPress: () => save({}) }}
    />
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24, backgroundColor: colors.background },
});
