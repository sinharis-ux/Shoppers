import React, { useState, useEffect } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, StatusBar, Image, ScrollView, TextInput, Platform, Alert, ActivityIndicator } from 'react-native';
import { Images } from '../Assets/index';
import { ApiConstants } from '../Theme/ApiConstants';
import axios from 'axios';

type PersonImageMap = {
    front?: string;
    side?: string;
    back?: string;
    face?: string;
};

const Basicmeasurement = ({ navigation, route }: any) => {

    const [gender, setGender] = useState('Male');
    const [height_unit, setHeightUnit] = useState('inch');
    const [weight_unit, setWeightUnit] = useState('lbs');
    const [height, setHeight] = useState('');
    const [weight, setWeight] = useState('');
    const [shoulder, setShoulder] = useState('');
    const [chest, setChest] = useState('');
    const [waist, setWaist] = useState('');
    const [hips, setHips] = useState('');
    const [inseam, setInseam] = useState('');

    // Default values if passed
    const [selectedImageMap, setSelectedImageMap] = useState<PersonImageMap>({});
    const [sessionId, setSessionId] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    const normalizeImageMap = (map: PersonImageMap) => ({
        ...(map.front ? { front: map.front } : {}),
        ...(map.side ? { side: map.side } : {}),
        ...(map.back ? { back: map.back } : {}),
        ...(map.face ? { face: map.face } : {}),
    });

    const mapFromUris = (uris: string[]) => normalizeImageMap({
        front: uris[0],
        side: uris[1],
        back: uris[2],
        face: uris[3],
    });

    const appendImageField = (formData: FormData, fieldName: string, uri: string) => {
        const cleanUri = Platform.OS === 'android' ? uri : uri.replace('file://', '');
        formData.append(fieldName, {
            uri: Platform.OS === 'android' ? uri : cleanUri,
            type: 'image/jpeg',
            name: `${fieldName}_${Date.now()}.jpg`,
        } as any);
    };

    useEffect(() => {
        console.log("🟢 Basicmeasurement params:", JSON.stringify(route.params, null, 2));

        if (route.params?.sessionId) {
            setSessionId(route.params.sessionId);
        }
        let incomingMap: PersonImageMap | null = null;

        if (route.params?.selectedImageMap) {
            incomingMap = normalizeImageMap(route.params.selectedImageMap);
        } else {
            const incomingUris = Array.isArray(route.params?.selectedImageUris)
                ? route.params.selectedImageUris
                : route.params?.selectedImageUri
                    ? [route.params.selectedImageUri]
                    : [];

            if (incomingUris.length > 0) {
                incomingMap = mapFromUris(incomingUris.filter(Boolean).slice(0, 4));
            }
        }

        if (incomingMap) {
            setSelectedImageMap(incomingMap);
            console.log("📸 Received images to process:", incomingMap);
        }
    }, [route.params]);

    const handleBack = () => {
        navigation.goBack();
    };

    const handleCreateAvatar = async () => {
        const orderedUris = [
            selectedImageMap.front,
            selectedImageMap.side,
            selectedImageMap.back,
            selectedImageMap.face,
        ].filter((uri): uri is string => Boolean(uri));

        if (orderedUris.length === 0 || !sessionId) {
            Alert.alert("Missing Data", "Please add at least one photo first.");
            return;
        }

        setLoading(true);
        console.log("🚀 Starting Avatar Generation with Measurements...");

        try {
            const formData = new FormData();

            const imageFieldMap: Record<string, string | undefined> = {
                image_front: selectedImageMap.front,
                image_side: selectedImageMap.side,
                image_back: selectedImageMap.back,
                image_face: selectedImageMap.face,
            };

            Object.entries(imageFieldMap).forEach(([fieldName, uri]) => {
                if (uri) {
                    appendImageField(formData, fieldName, uri);
                }
            });

            if (orderedUris.length === 1) {
                appendImageField(formData, "image", orderedUris[0]);
            }

            formData.append("session_id", sessionId);

            // Add Measurements
            formData.append("gender", gender);
            formData.append("height", height || "170"); // Default if empty
            formData.append("weight", weight || "65");
            formData.append("chest", chest || "");
            formData.append("waist", waist || "");
            formData.append("hips", hips || "");
            formData.append("height_unit", height_unit === 'inch' ? 'in' : 'cm');
            formData.append("weight_unit", weight_unit === 'lbs' ? 'lbs' : 'kg');

            // Construct a descriptive prompt for the backend
            // You can also send raw fields if backend handles it, 
            // but for now we send raw fields and let backend format.

            console.log("📡 Sending API Request to:", `${ApiConstants.BASE_URL}${ApiConstants.GENERATE_AVATAR}`);

            const response = await axios.post(
                `${ApiConstants.BASE_URL}${ApiConstants.GENERATE_AVATAR}`,
                formData,
                {
                    headers: {
                        "Content-Type": "multipart/form-data",
                        Accept: "application/json",
                    },
                }
            );

            console.log("✅ API Response:", response.data);

            if (response.data.status === "success" || response.data.avatar_url) {
                const fullAvatarUrl = response.data.avatar_url.startsWith("http")
                    ? response.data.avatar_url
                    : `${ApiConstants.IMAGE_URL}${response.data.avatar_url}`;

                // Navigate to Avatar screen
                navigation.navigate('Avatar', {
                    sessionId: sessionId,
                    avatar_url: fullAvatarUrl,
                    avatarImageBase64: response.data.saved_path,
                    is_full_body: response.data.is_full_body,
                });
            } else {
                Alert.alert("Error", response.data.message || "Avatar generation failed.");
            }

        } catch (error: any) {
            console.error("❌ API Error:", error.response?.data || error.message);
            Alert.alert("Error", "Failed to generate avatar. " + (error.response?.data?.message || error.message));
        } finally {
            setLoading(false);
        }
    };

    const handleGenderChange = () => {
        setGender(prev => prev === 'Female' ? 'Male' : 'Female');
    };

    const handleHeightUnitChange = () => {
        setHeightUnit(prev => prev === 'inch' ? 'cm' : 'inch');
    };

    const handleWeightUnitChange = () => {
        setWeightUnit(prev => prev === 'lbs' ? 'kg' : 'lbs');
    };

    // Helper to render input rows
    const renderInputRow = (label: string, value: string, setValue: (val: string) => void, placeholder: string = "In inch") => (
        <View style={styles.measurementItem}>
            <Text style={styles.measurementLabel}>{label}</Text>
            <TextInput
                style={styles.input}
                value={value}
                onChangeText={setValue}
                placeholder={placeholder}
                placeholderTextColor="#A6A6A6"
                keyboardType="numeric"
            />
            <View style={styles.divider} />
        </View>
    );

    return (
        <View style={styles.container}>
            <StatusBar barStyle="dark-content" backgroundColor="#fff" />

            <View style={styles.header}>
                <TouchableOpacity onPress={handleBack} style={styles.backButton}>
                    <Image
                        source={Images.img_Chevron}
                        style={styles.backIcon}
                        resizeMode="contain"
                    />
                </TouchableOpacity>
            </View>

            <View style={styles.titleContainer}>
                <Text style={styles.headerTitle}>Basic Measurements</Text>
            </View>

            {/* Loading Overlay */}
            {loading && (
                <View style={styles.loadingOverlay}>
                    <ActivityIndicator size="large" color="#DB3022" />
                    <Text style={styles.loadingText}>Creating your realistic avatar...{'\n'}This may take up to 30 seconds.</Text>
                </View>
            )}

            <ScrollView
                style={styles.content}
                showsVerticalScrollIndicator={false}
            >
                {[selectedImageMap.front, selectedImageMap.side, selectedImageMap.back, selectedImageMap.face].some(Boolean) && (
                    <View style={styles.imagePreviewRow}>
                        <Image
                            source={{
                                uri: (selectedImageMap.front || selectedImageMap.side || selectedImageMap.back || selectedImageMap.face || '').includes('?')
                                    ? `${selectedImageMap.front || selectedImageMap.side || selectedImageMap.back || selectedImageMap.face}&t=${Date.now()}`
                                    : `${selectedImageMap.front || selectedImageMap.side || selectedImageMap.back || selectedImageMap.face}?t=${Date.now()}`
                            }}
                            style={styles.thumbnail}
                        />
                        <Text style={styles.thumbnailText}>
                            {[selectedImageMap.front, selectedImageMap.side, selectedImageMap.back, selectedImageMap.face].filter(Boolean).length > 1
                                ? `${[selectedImageMap.front, selectedImageMap.side, selectedImageMap.back, selectedImageMap.face].filter(Boolean).length} photos ready (front, side, back, face order)`
                                : 'Photo ready'}
                        </Text>
                    </View>
                )}

                <View style={styles.measurementsContainer}>

                    {/* Unit Selectors at Top */}
                    <View style={styles.unitSelectorContainer}>
                        <View style={styles.unitSelectorRow}>
                            <Text style={styles.unitLabel}>Height Unit:</Text>
                            <TouchableOpacity
                                style={styles.unitButton}
                                onPress={handleHeightUnitChange}
                            >
                                <Text style={styles.unitValue}>{height_unit === 'inch' ? 'Inch' : 'Centimeter'}</Text>
                                <Image
                                    source={Images.img_dropdown}
                                    style={styles.dropdownIcon}
                                    resizeMode="contain"
                                />
                            </TouchableOpacity>
                        </View>
                        <View style={styles.unitSelectorRow}>
                            <Text style={styles.unitLabel}>Weight Unit:</Text>
                            <TouchableOpacity
                                style={styles.unitButton}
                                onPress={handleWeightUnitChange}
                            >
                                <Text style={styles.unitValue}>{weight_unit === 'lbs' ? 'lbs' : 'Kilogram'}</Text>
                                <Image
                                    source={Images.img_dropdown}
                                    style={styles.dropdownIcon}
                                    resizeMode="contain"
                                />
                            </TouchableOpacity>
                        </View>
                        <View style={styles.divider} />
                    </View>

                    {/* Height */}
                    {renderInputRow('Height', height, setHeight, `In ${height_unit === 'inch' ? 'inch' : 'cm'}`)}

                    {/* Weight */}
                    {renderInputRow('Weight', weight, setWeight, `In ${weight_unit}`)}

                    {/* Gender */}
                    <View style={styles.measurementItem}>
                        <Text style={styles.measurementLabel}>Gender</Text>
                        <TouchableOpacity
                            style={styles.genderButton}
                            onPress={handleGenderChange}
                        >
                            <Text style={styles.measurementValue}>{gender}</Text>
                            <Image
                                source={Images.img_dropdown}
                                style={styles.dropdownIcon}
                                resizeMode="contain"
                            />
                        </TouchableOpacity>
                        <View style={styles.divider} />
                    </View>

                    {/* Other measurements */}
                    {renderInputRow('Shoulder Width', shoulder, setShoulder)}
                    {renderInputRow('Chest / Bust', chest, setChest)}
                    {renderInputRow('Waist', waist, setWaist)}
                    {renderInputRow('Hips', hips, setHips)}
                    {renderInputRow('Inseam (leg length)', inseam, setInseam)}

                </View>

                <TouchableOpacity
                    style={[styles.createButton, loading && styles.disabledButton]}
                    onPress={handleCreateAvatar}
                    disabled={loading}
                >
                    <Text style={styles.createButtonText}>
                        {loading ? "GENERATING..." : "CREATE AN AVATAR"}
                    </Text>
                </TouchableOpacity>

                <View style={styles.bottomSpacing} />
            </ScrollView>
        </View>
    );
};

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: '#fff',
    },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: 20,
        paddingTop: Platform.OS === 'ios' ? 60 : 50,
        paddingBottom: 10,
    },
    backButton: {
        padding: 5,
    },
    backIcon: {
        width: 16,
        height: 16,
    },
    titleContainer: {
        paddingHorizontal: 20,
        paddingBottom: 20,
        borderBottomWidth: 1,
        borderBottomColor: '#f0f0f0',
    },
    headerTitle: {
        fontSize: 22,
        fontWeight: 'bold',
        color: '#000',
        textAlign: 'left',
    },
    content: {
        flex: 1,
        paddingHorizontal: 20,
    },
    measurementsContainer: {
        marginTop: 20,
    },
    unitSelectorContainer: {
        marginBottom: 20,
        paddingBottom: 10,
    },
    unitSelectorRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 15,
    },
    unitLabel: {
        fontSize: 16,
        fontWeight: '500',
        color: '#1A1A1A',
    },
    unitButton: {
        flexDirection: 'row',
        alignItems: 'center',
    },
    unitValue: {
        fontSize: 16,
        color: '#1A1A1A',
        marginRight: 8,
    },
    measurementItem: {
        marginBottom: 5,
    },
    measurementLabel: {
        fontSize: 16,
        fontWeight: '500',
        color: '#1A1A1A',
        marginBottom: 8,
    },
    measurementValue: {
        fontSize: 16,
        color: '#1A1A1A',
        marginBottom: 8,
    },
    input: {
        fontSize: 16,
        color: '#1A1A1A',
        marginBottom: 8,
        padding: 0,
    },
    genderButton: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 8,
    },
    dropdownIcon: {
        width: 12,
        height: 12,
        tintColor: '#666',
        marginLeft: 10,
    },
    divider: {
        height: 1,
        backgroundColor: '#E0E0E0',
        marginBottom: 20,
    },
    createButton: {
        backgroundColor: '#DB3022',
        paddingVertical: 16,
        borderRadius: 27,
        alignItems: 'center',
        marginTop: 30,
        marginBottom: 20,
    },
    disabledButton: {
        opacity: 0.7
    },
    createButtonText: {
        color: '#fff',
        fontSize: 15,
        fontWeight: '600',
        letterSpacing: 0.5,
    },
    bottomSpacing: {
        height: 40,
    },
    loadingOverlay: {
        position: 'absolute',
        top: 0, left: 0, right: 0, bottom: 0,
        backgroundColor: 'rgba(255,255,255,0.9)',
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: 100,
    },
    loadingText: {
        marginTop: 20,
        fontSize: 16,
        color: '#000',
        textAlign: 'center',
        fontWeight: '500'
    },
    imagePreviewRow: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: 10,
    },
    thumbnail: {
        width: 40,
        height: 40,
        borderRadius: 5,
        marginRight: 10
    },
    thumbnailText: {
        color: '#666'
    }
});

export default Basicmeasurement;
