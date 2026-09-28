import Ionicons from '@expo/vector-icons/Ionicons';
import { ComponentProps, useEffect, useState } from 'react';
import { Animated, Easing, Pressable, StyleSheet, View } from 'react-native';

import { colors } from '@/constants/colors';

// Every state the big mic button can show. Home computes this from the
// recorder hook (recording) and the conversation store (everything else).
export type MicState =
  | 'idle'
  | 'recording'
  | 'transcribing'
  | 'sending'
  | 'waiting'
  | 'speaking'
  | 'error';

type IconName = ComponentProps<typeof Ionicons>['name'];

const LOOK: Record<MicState, { color: string; icon: IconName; label: string }> = {
  idle: { color: colors.primary, icon: 'mic', label: 'Start recording' },
  recording: { color: colors.recording, icon: 'stop', label: 'Stop recording' },
  transcribing: { color: colors.transcribing, icon: 'text', label: 'Transcribing' },
  sending: { color: colors.sending, icon: 'arrow-up', label: 'Sending' },
  waiting: { color: colors.sending, icon: 'hourglass-outline', label: 'Waiting for reply' },
  speaking: { color: colors.speaking, icon: 'volume-high', label: 'Speaking, tap to interrupt' },
  error: { color: colors.recording, icon: 'mic', label: 'Try again' },
};

const SIZE = 96;

// React Native's built-in Animated API: an Animated.Value is a number that
// animates on the native UI thread (useNativeDriver) so it stays smooth even
// while JavaScript is busy with network calls.
export function MicButton({
  state,
  onPress,
  disabled,
}: {
  state: MicState;
  onPress: () => void;
  disabled?: boolean;
}) {
  // useState with an initializer function creates each value exactly once and
  // keeps it for the component's lifetime (the React Compiler-friendly way;
  // reading useRef().current during render is not allowed).
  const [pulse] = useState(() => new Animated.Value(0)); // 0→1 repeating ring
  const [spin] = useState(() => new Animated.Value(0)); // 0→1 repeating rotation
  const [shake] = useState(() => new Animated.Value(0)); // one-off error shake

  const pulsing = state === 'recording' || state === 'speaking';
  const spinning = state === 'transcribing' || state === 'sending' || state === 'waiting';

  useEffect(() => {
    if (!pulsing) return;
    pulse.setValue(0);
    const loop = Animated.loop(
      Animated.timing(pulse, {
        toValue: 1,
        duration: state === 'recording' ? 1100 : 1500,
        easing: Easing.out(Easing.ease),
        useNativeDriver: true,
      }),
    );
    loop.start();
    return () => loop.stop();
  }, [pulsing, state, pulse]);

  useEffect(() => {
    if (!spinning) return;
    spin.setValue(0);
    const loop = Animated.loop(
      Animated.timing(spin, {
        toValue: 1,
        duration: 1000,
        easing: Easing.linear,
        useNativeDriver: true,
      }),
    );
    loop.start();
    return () => loop.stop();
  }, [spinning, spin]);

  useEffect(() => {
    if (state !== 'error') return;
    shake.setValue(0);
    Animated.sequence(
      [1, -1, 1, -1, 0].map((toValue) =>
        Animated.timing(shake, { toValue, duration: 60, useNativeDriver: true }),
      ),
    ).start();
  }, [state, shake]);

  const look = LOOK[state];

  return (
    <View style={styles.wrapper}>
      {pulsing && (
        <Animated.View
          pointerEvents="none"
          style={[
            styles.ring,
            {
              backgroundColor: look.color,
              opacity: pulse.interpolate({ inputRange: [0, 1], outputRange: [0.45, 0] }),
              transform: [{ scale: pulse.interpolate({ inputRange: [0, 1], outputRange: [1, 1.6] }) }],
            },
          ]}
        />
      )}
      {spinning && (
        <Animated.View
          pointerEvents="none"
          style={[
            styles.arc,
            {
              borderTopColor: look.color,
              transform: [
                { rotate: spin.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '360deg'] }) },
              ],
            },
          ]}
        />
      )}
      <Animated.View
        style={{
          transform: [{ translateX: shake.interpolate({ inputRange: [-1, 1], outputRange: [-8, 8] }) }],
        }}>
        <Pressable
          onPress={onPress}
          disabled={disabled}
          accessibilityRole="button"
          accessibilityLabel={look.label}
          accessibilityState={{ disabled, busy: spinning }}
          style={({ pressed }) => [
            styles.button,
            { backgroundColor: look.color },
            state === 'error' && styles.errorOutline,
            (pressed || spinning) && styles.dimmed,
          ]}>
          <Ionicons name={look.icon} size={40} color="#fff" />
        </Pressable>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    width: SIZE + 40,
    height: SIZE + 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  ring: { position: 'absolute', width: SIZE, height: SIZE, borderRadius: SIZE / 2 },
  arc: {
    position: 'absolute',
    width: SIZE + 16,
    height: SIZE + 16,
    borderRadius: (SIZE + 16) / 2,
    borderWidth: 4,
    borderColor: 'transparent',
  },
  button: {
    width: SIZE,
    height: SIZE,
    borderRadius: SIZE / 2,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOpacity: 0.15,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 4 },
    elevation: 4,
  },
  errorOutline: { borderWidth: 3, borderColor: colors.dangerSoft },
  dimmed: { opacity: 0.8 },
});
