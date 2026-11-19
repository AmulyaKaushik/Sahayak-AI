import { useFocusEffect } from 'expo-router';
import { useCallback } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { NoticeCard } from '@/components/notice-card';
import { ProfileForm, useProfileData } from '@/components/profile-form';
import { colors } from '@/constants/colors';
import { updateProfile, type ProfileValue } from '@/services/api';

// Route "/profile" ("My details"): view and edit the saved profile. Facts told
// to the chatbot ("I am 35") are saved to the same place, so this screen
// reloads every time it comes into view to show the latest values.
export default function ProfileScreen() {
  const { schema, fields, setFields, version, loading, error, reload } = useProfileData();

  useFocusEffect(
    useCallback(() => {
      reload();
    }, [reload]),
  );

  async function save(updates: Record<string, ProfileValue>) {
    if (Object.keys(updates).length === 0) return;
    const response = await updateProfile(updates);
    // Keep the form mounted (so "Saved." stays visible); just update the
    // baseline that the next save compares against.
    setFields(response.fields);
  }

  if (!schema) {
    return (
      <View style={styles.center}>
        {loading ? (
          <ActivityIndicator size="large" color={colors.primary} />
        ) : (
          <NoticeCard
            tone="danger"
            message={error ?? 'Could not load your details.'}
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
      intro="Sahayak uses these details to check your eligibility. Details you tell Sahayak by voice appear here too."
      submitLabel="Save changes"
      onSubmit={save}
    />
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24, backgroundColor: colors.background },
});
