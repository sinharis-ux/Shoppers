import React, { useState, useEffect } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, StatusBar, Image, Platform, } from 'react-native';
import { Images } from '../Assets/index';

const Avatar = ({ navigation, route }: any) => {
    const [avatarImage, setAvatarImage] = useState<any>(null);
    const [sessionId, setSessionId] = useState<string | null>(null);

    useEffect(() => {
        console.log('🟢 AVATAR PARAMS:', route?.params);

        if (route?.params?.sessionId) {
            console.log("✅ Session ID received in Avatar:", route.params.sessionId);
            setSessionId(route.params.sessionId);
        } else {
            console.log("❌ No sessionId found in Avatar params");
        }
        if (route?.params?.tryonUrl) {
            setAvatarImage({ uri: route.params.tryonUrl });
        } else if (route?.params?.avatar_url) {
            setAvatarImage({ uri: route.params.avatar_url });
        } else {
            setAvatarImage(null);
        }

    }, [route?.params]);

    const handleBack = () => {
        navigation.goBack();
    };

    const handleCreateAvatar = () => {
        if (!sessionId) {
            console.error("❌ No sessionId available for navigation to Productlist");
            return;
        }

        console.log("🎬 Navigating to Productlist with sessionId:", sessionId);

        navigation.navigate('Productlist', {
            sessionId: sessionId, // ✅ यहाँ से Productlist को sessionId भेजें
            avatarImage: avatarImage?.uri,
        });
    };

    const handleRetakePhoto = () => {
        setAvatarImage(null);
        navigation.goBack(); 
    };

    return (
        <View style={styles.container}>
            <StatusBar barStyle="dark-content" backgroundColor="#fff" />

           <View style={styles.header}>
                <TouchableOpacity onPress={handleBack}>
                    <Image source={Images.img_Chevron} />
                </TouchableOpacity>

                <Text style={styles.headerTitle}>Your Avatar</Text>

                {avatarImage && (
                    <TouchableOpacity onPress={handleRetakePhoto}>
                        <Text style={styles.retakeText}>Retake</Text>
                    </TouchableOpacity>
                )}
            </View>

            <View style={styles.avatarContainer}>
                {!avatarImage ? (
                    <Text style={styles.placeholderText}>
                        No avatar generated yet
                    </Text>
                ) : (
                    <Image
                        source={avatarImage}
                        style={styles.avatarImage}
                        resizeMode="contain"
                    />
                )}
            </View>

            <View style={styles.footer}>
                <TouchableOpacity
                    disabled={!avatarImage}
                    onPress={handleCreateAvatar}
                >
                    <View
                        style={[
                            styles.searchBarContainer,
                            { opacity: avatarImage ? 1 : 0.4 },
                        ]}
                    >
                        <Image
                            source={Images.img_searchbar}
                            style={styles.searchbar}
                        />
                    </View>
                </TouchableOpacity>
            </View>
        </View>
    );
};

export default Avatar;

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: '#fff',
    },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: 20,
        paddingTop: Platform.OS === 'ios' ? 60 : 50,
        paddingBottom: 20,
    },
    headerTitle: {
        fontSize: 18,
        color: '#000',
        fontWeight: '600',
        flex: 1,
        textAlign: 'center',
    },
    retakeText: {
        color: '#DB3022',
        fontSize: 16,
        fontWeight: '500',
    },
    avatarContainer: {
        flex: 1,
        backgroundColor: '#DCDEE0',
        justifyContent: 'center',
        alignItems: 'center',
    },
    avatarImage: {
        width: '100%',
        height: '95%',
    },
    uploadButton: {
        width: 200,
        height: 50,
        backgroundColor: '#DB3022',
        borderRadius: 25,
        justifyContent: 'center',
        alignItems: 'center',
    },
    uploadText: {
        color: '#fff',
        fontSize: 16,
        fontWeight: '600',
    },
    footer: {
        backgroundColor: '#fff',
        height: 120,
        alignItems: 'center',
        paddingBottom: 20,
    },
    searchBarContainer: {
        width: 55,
        height: 55,
        borderRadius: 30,
        backgroundColor: '#DB3022',
        justifyContent: 'center',
        alignItems: 'center',
        marginTop: 10,
    },
    searchbar: {
        width: 19,
        height: 19,
        tintColor: '#FFFFFF',
    },
});