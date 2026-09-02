import React from 'react';
import { StatusBar, StyleSheet, View } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import Takephoto from './Src/Screens/Takephoto';
import Phototaken from './Src/Screens/Phototaken';
import Basicmeasurement from './Src/Screens/Basicmeasurement';
import Avatar from './Src/Screens/Avatar';
import Productlist from './Src/Screens/Productlist';

const Stack = createNativeStackNavigator();

function App() {
  return (
    <View style={styles.container}>
      <NavigationContainer>
        <Stack.Navigator
          initialRouteName="Takephoto"
          screenOptions={{
            headerShown: false
          }}
        >
          <Stack.Screen name="Takephoto" component={Takephoto} />
          <Stack.Screen name="Phototaken" component={Phototaken} />
          <Stack.Screen name="Basicmeasurement" component={Basicmeasurement} />
          <Stack.Screen name="Avatar" component={Avatar} />
          <Stack.Screen name="Productlist" component={Productlist} />

        </Stack.Navigator>
      </NavigationContainer>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
});

export default App;