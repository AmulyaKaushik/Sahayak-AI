import { StyleSheet, Text, View } from 'react-native';

// Settings screen (route "/settings"). Mock/real backend toggle, language
// preference, etc. will be added here in later phases.
export default function SettingsScreen() {
  return (
    <View style={styles.container}>
      <Text style={styles.text}>Settings will go here.</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
    backgroundColor: '#fff',
  },
  text: { fontSize: 16, color: '#666' },
});
