import React from 'react';
import { View, Image, StyleSheet, TouchableOpacity, Text, Alert } from 'react-native';
import { useRoute, useNavigation } from '@react-navigation/native';

const BASE_URL = 'http://168.231.121.7';
const HARDCODED_PRODUCT_ID = "4698458";

const TryOnScreen = () => {
    const route = useRoute();
    const navigation = useNavigation();
    
    const { tryon_url } = route.params as {
        tryon_url: string;
    };

    console.log('TryOnScreen - Using hardcoded product ID:', HARDCODED_PRODUCT_ID);
    console.log('TryOnScreen - TryOn URL:', tryon_url);

    const handleBuyNow = () => {
        Alert.alert(
            'Buy Now',
            `Product ID: ${HARDCODED_PRODUCT_ID}\nDo you want to proceed to purchase?`,
            [
                { text: 'Cancel', style: 'cancel' },
                {
                    text: 'Buy', 
                    onPress: () => {
                        console.log('Purchasing product:', HARDCODED_PRODUCT_ID);
                        // Add purchase logic here
                    }
                }
            ]
        );
    };

    return (
        <View style={styles.container}>
            <TouchableOpacity style={styles.backButton} onPress={() => navigation.goBack()}>
                <Text style={{ color: 'white' }}>Back</Text>
            </TouchableOpacity>

            {tryon_url ? (
                <Image
                    source={{ uri: `${BASE_URL}${tryon_url}` }}
                    style={styles.tryonImage}
                    resizeMode="contain"
                    onLoad={() => console.log('Image loaded successfully')}
                    onError={(e) => console.log('Image loading error:', e.nativeEvent.error)}
                />
            ) : (
                <View style={styles.errorContainer}>
                    <Text style={styles.errorText}>No try-on image available</Text>
                </View>
            )}

            {/* Always show hardcoded product ID */}
            <View style={styles.productInfo}>
                <Text style={styles.productId}>Hardcoded Product ID: {HARDCODED_PRODUCT_ID}</Text>
            </View>

            {/* Buy Now Button */}
            <TouchableOpacity style={styles.buyButton} onPress={handleBuyNow}>
                <Text style={styles.buyButtonText}>Buy Now</Text>
            </TouchableOpacity>
        </View>
    );
};

export default TryOnScreen;