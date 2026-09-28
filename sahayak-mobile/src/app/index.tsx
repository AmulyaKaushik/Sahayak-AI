import { Link } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';

// Home screen (route "/"). The mic button and chat transcript will live here.
export default function HomeScreen() {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>Sahayak AI</Text>
      <Text style={styles.subtitle}>Voice banking assistant</Text>

      <Link href="/settings" asChild>
        <Pressable style={styles.button}>
          <Text style={styles.buttonText}>Open Settings</Text>
        </Pressable>
      </Link>
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
  title: { fontSize: 28, fontWeight: '700' },
  subtitle: { fontSize: 16, color: '#666', marginTop: 4, marginBottom: 32 },
  button: {
    backgroundColor: '#208AEF',
    paddingVertical: 12,
    paddingHorizontal: 24,
    borderRadius: 8,
  },
  buttonText: { color: '#fff', fontSize: 16, fontWeight: '600' },
});
