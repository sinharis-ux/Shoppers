// import React, { useState, useEffect } from 'react';
// import { View, Text, TouchableOpacity, StyleSheet, StatusBar, Image, Alert, Platform, ActivityIndicator } from 'react-native';
// import { useNavigation, useRoute } from '@react-navigation/native';
// import { launchCamera, launchImageLibrary } from "react-native-image-picker";
// import { PermissionsAndroid } from 'react-native';
// import { Images } from '../Assets/Images';
// import AsyncStorage from '@react-native-async-storage/async-storage';
// import { ApiConstants } from '../Theme/ApiConstants';

// const Phototaken = () => {
//     const navigation = useNavigation<any>();
//     const route = useRoute<any>();

//     const [imageUri, setImageUri] = useState<string | null>(null);
//     const [cameraType, setCameraType] = useState('back');
//     const [flashMode, setFlashMode] = useState('off');
//     const [loading, setLoading] = useState(false);
//     const [sessionId, setSessionId] = useState<string | null>(null);
//

//     useEffect(() => {
//         const loadSession = async () => {
//             const id = await AsyncStorage.getItem('@app:session_id');
//             console.log("📦 Loaded Session from storage:", id);
//             setSessionId(id);
//         };
//         loadSession();
//     }, []);


//     useEffect(() => {
//     if (route.params?.selectedImageUri) {
//         console.log("Gallery Image Received:", route.params.selectedImageUri);
//         setImageUri(route.params.selectedImageUri);
//     }
// }, [route.params]);



//     const checkCameraPermission = async () => {
//         if (Platform.OS === 'android') {
//             const granted = await PermissionsAndroid.request(
//                 PermissionsAndroid.PERMISSIONS.CAMERA
//             );

//             return granted === PermissionsAndroid.RESULTS.GRANTED;
//         }
//         return true;
//     };

//     const openCamera = async () => {
//         const permission = await checkCameraPermission();
//         if (!permission) return;

//         launchCamera(
//             {
//                 mediaType: "photo",
//                 cameraType,
//                 saveToPhotos: false,
//                 quality: 0.8,
//                 flashMode,
//             },
//             (response) => {
//                 if (response.assets) {
//                     const uri: any = response.assets[0].uri;
//                     setImageUri(uri);
//                     console.log("Photo clicked:", uri);
//                 }
//             }
//         );
//     };


//     const generateAvatar = async () => {
//         console.log("photoUri in generateAvatar", imageUri);
//         console.log("sessionId in generateAvatar", sessionId);

//         setLoading(true);
//         try {
//             const formData = new FormData();

//             formData.append("photo", {
//                 uri: imageUri,
//                 type: "image/jpeg",
//                 name: "photo.jpg",
//             });

//             // Load session directly from storage
//             const sessionId = await AsyncStorage.getItem('@app:session_id');
//             formData.append("session_id", sessionId);

//             console.log("🔍 Sending Session:", sessionId);
//             console.log("🔍 Sending Photo:",  imageUri);
//             console.log("formData before sending:",formData);


//             const response = await fetch(
//                 `${ApiConstants.BASE_URL}${ApiConstants.GENERATE_AVATAR}`,
//                 {
//                     method: "POST",
//                     headers: {
//                         'Content-Type': 'multipart/form-data',
//                     },
//                     body: formData,
//                 }
//             );

//             const raw = await response.text();
//             console.log("📥 RAW RESPONSE:", raw);

//             const data = JSON.parse(raw);

//             if (data.status === "success") {
//                 return data;
//             } else {
//                 throw new Error("Avatar generation failed");
//             }
//         } catch (error) {
//             console.error("API Error:", error);
//             Alert.alert("Error", "Failed to generate avatar. Please try again.");
//             return null;
//         } finally {
//             setLoading(false);
//         }
//     };



//     const handleUsePhoto = async () => {
//         if (imageUri) {
//             setLoading(true);

//             try {
//                 const avatarData = await generateAvatar();
//                 console.log("avatarData in handleUsePhoto:",avatarData);


//                 if (avatarData) {
//                     console.log("Navigating to Avatar screen with avatar data:", avatarData);
//                     navigation.navigate("Basicmeasurement", {
//                         selectedImageUri: imageUri,
//                         avatarImageUrl: avatarData.image_url,
//                         avatarImageBase64: avatarData.image_base64,
//                         source: 'camera'
//                     });
//                 }
//             } catch (error) {
//                 console.error('Error in handleUsePhoto:', error);
//                 Alert.alert('Error', 'Something went wrong. Please try again.');
//             } finally {
//                 setLoading(false);
//             }
//         }
//     };

//     const handleBack = () => {
//         navigation.goBack();
//     };

//     return (
//         <View style={styles.container}>
//             <StatusBar barStyle="light-content" backgroundColor="#fff" />

//             <View style={styles.header}>
//                 <TouchableOpacity onPress={handleBack}>
//                     <Image source={Images.img_Chevron} />
//                 </TouchableOpacity>
//                 <Text style={styles.headerTitle}>Visual search</Text>

//                 <Image
//                     source={Images.img_search}
//                     style={styles.flashText}
//                     resizeMode="contain"
//                 />
//             </View>

//             {loading ? (
//                 <View style={styles.loadingContainer}>
//                     <ActivityIndicator size="large" color="#000" />
//                     <Text style={styles.loadingText}>Generating Avatar...</Text>
//                 </View>
//             ) : imageUri ? (
//                 <View style={{ flex: 1 }}>
//                     <Image source={{ uri: imageUri }} style={styles.previewImage} />

//                     <View style={styles.previewControls}>
//                         <TouchableOpacity style={styles.retakeButton} onPress={() => setImageUri(null)}>
//                             <Text style={styles.retakeText}>Retake</Text>
//                         </TouchableOpacity>

//                         <TouchableOpacity style={styles.useButton} onPress={handleUsePhoto} disabled={loading}>
//                             <Text style={styles.useText}>
//                                 {loading ? 'Processing...' : 'Use Photo'}
//                             </Text>
//                         </TouchableOpacity>
//                     </View>
//                 </View>
//             ) : (
//                 <View style={styles.cameraBox}>
//                     <View style={styles.captureRow}>
//                         <TouchableOpacity onPress={() => setFlashMode(flashMode === 'off' ? 'on' : 'off')}>
//                             <Image source={Images.img_flash} style={styles.sideIcon} />
//                         </TouchableOpacity>

//                         <TouchableOpacity style={styles.captureButton} onPress={openCamera}>
//                             <Image source={Images.img_Camera} style={styles.captureCircle} />
//                         </TouchableOpacity>

//                         <TouchableOpacity onPress={() => setCameraType(cameraType === 'back' ? 'front' : 'back')}>
//                             <Image source={Images.img_retake} style={styles.sideIcon1} />
//                         </TouchableOpacity>
//                     </View>
//                 </View>
//             )}
//         </View>
//     );
// };

// const styles = StyleSheet.create({
//     container: {
//         flex: 1,
//         backgroundColor: '#fff'
//     },
//     header: {
//         flexDirection: 'row',
//         justifyContent: 'space-between',
//         alignItems: 'center',
//         paddingHorizontal: 20,
//         paddingTop: 50,
//     },
//     headerTitle: {
//         fontSize: 18,
//         color: '#000',
//         fontWeight: '600'
//     },
//     flashText: {
//         color: '#fff',
//         fontSize: 16
//     },
//     cameraBox: {
//         flex: 1,
//         justifyContent: 'flex-end',
//         alignItems: "center",
//         borderColor: '#444',
//         borderRadius: 10,
//         marginBottom: 40
//     },
//     placeholderText: {
//         color: '#000',
//         marginBottom: 20,
//         fontSize: 20
//     },
//     captureRow: {
//         flexDirection: 'row',
//         justifyContent: 'space-between',
//         alignItems: 'center',
//         width: '55%'
//     },
//     sideIcon: {
//         padding: 10,
//         height: 30,
//         width: 10,
//         tintColor: '#000'
//     },
//     sideIcon1: {
//         padding: 10,
//         height: 27,
//         width: 28,
//         tintColor: '#000'
//     },
//     captureButton: {
//         justifyContent: 'center',
//         alignItems: 'center',
//         height: 70,
//         width: 70
//     },
//     captureCircle: {
//         width: 70,
//         height: 70,
//         borderRadius: 35,
//         backgroundColor: '#000'
//     },
//     previewImage: {
//         width: '100%',
//         height: '80%',
//         resizeMode: 'cover'
//     },
//     previewControls: {
//         flexDirection: 'row',
//         justifyContent: 'space-around',
//         padding: 20,
//         backgroundColor: '#000'
//     },
//     retakeButton: {
//         borderColor: '#fff',
//         borderWidth: 1,
//         paddingHorizontal: 25,
//         paddingVertical: 10,
//         borderRadius: 20
//     },
//     retakeText: {
//         color: '#fff',
//         fontSize: 16
//     },
//     useButton: {
//         backgroundColor: '#DB3022',
//         paddingHorizontal: 25,
//         paddingVertical: 10,
//         borderRadius: 20
//     },
//     useText: {
//         color: '#fff',
//         fontSize: 16
//     },
//     loadingContainer: {
//         flex: 1,
//         justifyContent: 'center',
//         alignItems: 'center'
//     },
//     loadingText: {
//         marginTop: 10,
//         fontSize: 16,
//         color: '#000'
//     }
// });

// export default Phototaken;


import React, { useState, useEffect } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, StatusBar, Image, Platform } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { launchCamera, launchImageLibrary } from "react-native-image-picker";
import { PermissionsAndroid } from 'react-native';
import { Images } from '../Assets/index';
import AsyncStorage from '@react-native-async-storage/async-storage';

const CAPTURE_STEPS = [
    { key: 'front', label: 'Front' },
    { key: 'side', label: 'Side' },
    { key: 'back', label: 'Back' },
    { key: 'face', label: 'Face' },
] as const;

type CaptureKey = typeof CAPTURE_STEPS[number]['key'];

const Phototaken = () => {
    const navigation = useNavigation<any>();
    const route = useRoute<any>();

    const [capturedImages, setCapturedImages] = useState<Record<CaptureKey, string | null>>({
        front: null,
        side: null,
        back: null,
        face: null,
    });
    const [currentStepIndex, setCurrentStepIndex] = useState(0);
    const [cameraType, setCameraType] = useState('back');
    const [flashMode, setFlashMode] = useState('off');
    const [sessionId, setSessionId] = useState<string | null>(null);
    const [swapSourceIndex, setSwapSourceIndex] = useState<number | null>(null);

    useEffect(() => {
        const loadSession = async () => {
            const id = await AsyncStorage.getItem('@app:session_id');
            console.log("📦 Loaded Session:", id);
            setSessionId(id);
        };
        loadSession();
    }, []);

    useEffect(() => {
        if (route.params?.selectedImageMap) {
            console.log("📸 Gallery Image Map Received:", route.params.selectedImageMap);
            const mappedImages = {
                front: route.params.selectedImageMap.front || null,
                side: route.params.selectedImageMap.side || null,
                back: route.params.selectedImageMap.back || null,
                face: route.params.selectedImageMap.face || null,
            };
            setCapturedImages(mappedImages);
            const nextIndex = CAPTURE_STEPS.findIndex(step => !mappedImages[step.key]);
            setCurrentStepIndex(nextIndex === -1 ? CAPTURE_STEPS.length - 1 : nextIndex);
        } else if (Array.isArray(route.params?.selectedImageUris)) {
            console.log("📸 Gallery Images Received:", route.params.selectedImageUris);
            const orderedUris = route.params.selectedImageUris.filter(Boolean).slice(0, 4);
            const mappedImages = {
                front: orderedUris[0] || null,
                side: orderedUris[1] || null,
                back: orderedUris[2] || null,
                face: orderedUris[3] || null,
            };
            setCapturedImages(mappedImages);
            const nextIndex = CAPTURE_STEPS.findIndex(step => !mappedImages[step.key]);
            setCurrentStepIndex(nextIndex === -1 ? CAPTURE_STEPS.length - 1 : nextIndex);
        } else if (route.params?.selectedImageUri) {
            console.log("📸 Gallery Image Received:", route.params.selectedImageUri);
            const mappedImages = {
                front: route.params.selectedImageUri,
                side: null,
                back: null,
                face: null,
            };
            setCapturedImages(mappedImages);
            setCurrentStepIndex(1);
        }
    }, [route.params]);

    const checkCameraPermission = async () => {
        if (Platform.OS === 'android') {
            const granted = await PermissionsAndroid.request(
                PermissionsAndroid.PERMISSIONS.CAMERA
            );
            return granted === PermissionsAndroid.RESULTS.GRANTED;
        }
        return true;
    };

    const openCamera = async (stepIndex: number = currentStepIndex) => {
        const permission = await checkCameraPermission();
        if (!permission) return;

        const stepKey = CAPTURE_STEPS[stepIndex]?.key || 'front';

        launchCamera(
            {
                mediaType: "photo",
                cameraType,
                quality: 0.8,
                maxWidth: 1536,
                maxHeight: 1536,
                flashMode,
            },
            (response) => {
                if (response.assets) {
                    const uri = response.assets[0].uri;
                    console.log("📸 Photo clicked:", uri);
                    if (uri) {
                        setCapturedImages(prev => {
                            const updated = { ...prev, [stepKey]: uri };
                            const nextIndex = CAPTURE_STEPS.findIndex(step => !updated[step.key]);
                            setCurrentStepIndex(nextIndex === -1 ? stepIndex : nextIndex);
                            return updated;
                        });
                    }
                }
            }
        );
    };


    const openGallery = async (stepIndex: number = currentStepIndex) => {
        const stepKey = CAPTURE_STEPS[stepIndex]?.key || 'front';
        launchImageLibrary(
            {
                mediaType: "photo",
                quality: 0.8,
            },
            (response) => {
                if (response.assets) {
                    const uri = response.assets[0].uri;
                    if (uri) {
                        setCapturedImages(prev => {
                            const updated = { ...prev, [stepKey]: uri };
                            const nextIndex = CAPTURE_STEPS.findIndex(step => !updated[step.key]);
                            setCurrentStepIndex(nextIndex === -1 ? stepIndex : nextIndex);
                            return updated;
                        });
                    }
                }
            }
        );
    };

    const removeImage = (stepKey: CaptureKey) => {
        setCapturedImages(prev => ({ ...prev, [stepKey]: null }));
        const index = CAPTURE_STEPS.findIndex(s => s.key === stepKey);
        setCurrentStepIndex(index);
        if (swapSourceIndex !== null) setSwapSourceIndex(null);
    };

    const handleThumbnailPress = (index: number) => {
        if (swapSourceIndex !== null) {
            if (swapSourceIndex === index) {
                setSwapSourceIndex(null); // Cancel
            } else {
                setCapturedImages(prev => {
                    const sourceKey = CAPTURE_STEPS[swapSourceIndex].key;
                    const targetKey = CAPTURE_STEPS[index].key;
                    return {
                        ...prev,
                        [sourceKey]: prev[targetKey],
                        [targetKey]: prev[sourceKey]
                    };
                });
                setSwapSourceIndex(null);
            }
        } else {
            setCurrentStepIndex(index);
        }
    };

    const handleThumbnailLongPress = (index: number) => {
        if (capturedImages[CAPTURE_STEPS[index].key]) {
            setSwapSourceIndex(index);
        }
    };

    const handleUsePhoto = () => {

        const orderedUris = CAPTURE_STEPS
            .map(step => capturedImages[step.key])
            .filter((uri): uri is string => Boolean(uri));

        if (orderedUris.length === 0) return; // Allow proceeding as long as at least 1 image is captured

        console.log("▶ Proceeding to measurements with images:", orderedUris);

        // Navigate to Basicmeasurement to capture details BEFORE generation
        navigation.navigate("Basicmeasurement", {
            sessionId: sessionId,
            selectedImageUris: orderedUris,
            selectedImageMap: capturedImages,
            source: "camera-or-gallery",
        });
    };

    const allCaptured = CAPTURE_STEPS.every(step => Boolean(capturedImages[step.key]));
    const currentStep = CAPTURE_STEPS[currentStepIndex] || CAPTURE_STEPS[0];
    const currentImageUri = capturedImages[currentStep.key];
    const nextMissingIndex = CAPTURE_STEPS.findIndex(step => !capturedImages[step.key]);
    const nextStep = nextMissingIndex === -1 ? null : CAPTURE_STEPS[nextMissingIndex];

    return (
        <View style={styles.container}>
            <StatusBar barStyle="dark-content" backgroundColor="#fff" />

            <View style={styles.header}>
                <TouchableOpacity onPress={() => navigation.goBack()}>
                    <Image source={Images.img_Chevron} />
                </TouchableOpacity>
                <Text style={styles.headerTitle}>Visual search</Text>
                <Image source={Images.img_search} style={styles.flashText} resizeMode="contain" />
            </View>

            <View style={styles.stepHeader}>
                <Text style={styles.stepTitle}>
                    {allCaptured
                        ? 'All photos captured'
                        : `Capture: ${currentStep.label} (${currentStepIndex + 1}/4)`}
                </Text>
                <Text style={styles.stepSubtitle}>Use back camera for front/side/back, front camera for face.</Text>
            </View>

            {swapSourceIndex !== null && (
                <View style={styles.swapBanner}>
                    <Text style={styles.swapText}>Tap another image to swap, or tap same to cancel</Text>
                </View>
            )}
            <View style={styles.stepRow}>
                {CAPTURE_STEPS.map((step, index) => {
                    const stepImage = capturedImages[step.key];
                    const isActive = index === currentStepIndex;
                    const isSwapping = index === swapSourceIndex;
                    return (
                        <TouchableOpacity
                            key={step.key}
                            style={[
                                styles.stepItem, 
                                isActive && styles.stepItemActive,
                                isSwapping && styles.stepItemSwapping
                            ]}
                            onPress={() => handleThumbnailPress(index)}
                            onLongPress={() => handleThumbnailLongPress(index)}
                            delayLongPress={300}
                        >
                            {stepImage ? (
                                <View style={styles.thumbnailContainer}>
                                    <Image source={{ uri: stepImage }} style={styles.stepThumbnail} />
                                    <TouchableOpacity 
                                        style={styles.removeIconContainer}
                                        onPress={() => removeImage(step.key)}
                                    >
                                        <Text style={styles.removeIconText}>✕</Text>
                                    </TouchableOpacity>
                                </View>
                            ) : (
                                <View style={styles.stepPlaceholder} />
                            )}
                            <Text style={styles.stepLabel}>{step.label}</Text>
                        </TouchableOpacity>
                    );
                })}
            </View>

            {currentImageUri ? (
                <View style={{ flex: 1 }}>
                    <Image
                        source={{
                            uri: currentImageUri.includes('?')
                                ? `${currentImageUri}&t=${Date.now()}`
                                : `${currentImageUri}?t=${Date.now()}`
                        }}
                        style={styles.previewImage}
                    />

                    <View style={styles.previewControls}>
                        <View style={styles.leftControls}>
                            <TouchableOpacity
                                style={styles.retakeButton}
                                onPress={() => openCamera(currentStepIndex)}
                            >
                                <Text style={styles.retakeText}>Retake</Text>
                            </TouchableOpacity>
                            <TouchableOpacity
                                style={styles.uploadButton}
                                onPress={() => openGallery(currentStepIndex)}
                            >
                                <Text style={styles.retakeText}>Upload</Text>
                            </TouchableOpacity>
                        </View>

                        <TouchableOpacity
                            style={styles.useButton}
                            onPress={handleUsePhoto}
                            disabled={!currentImageUri && orderedUris.length === 0} // In preview, there is always at least one image.
                        >
                            <Text style={styles.useText}>Use Photos</Text>
                        </TouchableOpacity>
                    </View>
                </View>
            ) : (
                <View style={styles.cameraBox}>
                    <View style={styles.captureRow}>
                        <TouchableOpacity onPress={() => setFlashMode(flashMode === 'off' ? 'on' : 'off')}>
                            <Image source={Images.img_flash} style={styles.sideIcon} />
                        </TouchableOpacity>

                        <TouchableOpacity style={styles.captureButton} onPress={() => openCamera(currentStepIndex)}>
                            <Image source={Images.img_Camera} style={styles.captureCircle} />
                        </TouchableOpacity>

                        <TouchableOpacity onPress={() => setCameraType(cameraType === 'back' ? 'front' : 'back')}>
                            <Image source={Images.img_retake} style={styles.sideIcon1} />
                        </TouchableOpacity>

                        <TouchableOpacity onPress={() => openGallery(currentStepIndex)} style={styles.galleryIconBtn}>
                            <Text style={styles.galleryIconText}>Upload</Text>
                        </TouchableOpacity>
                    </View>
                </View>
            )}
        </View>
    );
};

export default Phototaken;

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: '#fff'
    },
    header: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingHorizontal: 20,
        paddingTop: 50,
    },
    headerTitle: {
        fontSize: 18,
        color: '#000',
        fontWeight: '600'
    },
    flashText: {
        height: 20,
        width: 20
    },
    cameraBox: {
        flex: 1,
        justifyContent: 'flex-end',
        alignItems: "center",
        marginBottom: 40
    },
    captureRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        width: '80%' // Increased to fit 4 icons
    },
    galleryIconBtn: {
        justifyContent: 'center',
        alignItems: 'center',
    },
    galleryIconText: {
        color: '#DB3022',
        fontSize: 14,
        fontWeight: 'bold',
    },
    sideIcon: {
        height: 30,
        width: 20,
        tintColor: '#000'
    },
    sideIcon1: {
        height: 27,
        width: 28,
        tintColor: '#000'
    },
    captureButton: {
        height: 70,
        width: 70
    },
    captureCircle: {
        width: 70,
        height: 70,
        borderRadius: 35,
        backgroundColor: '#000'
    },
    previewImage: {
        width: '100%',
        height: '80%',
        resizeMode: 'cover'
    },
    previewControls: {
        flexDirection: 'row',
        justifyContent: 'space-around',
        padding: 20,
        backgroundColor: '#000'
    },
    retakeButton: {
        borderColor: '#fff',
        borderWidth: 1,
        paddingHorizontal: 25,
        paddingVertical: 10,
        borderRadius: 20
    },
    retakeText: {
        color: '#fff',
        fontSize: 16
    },
    useButton: {
        backgroundColor: '#DB3022',
        paddingHorizontal: 25,
        paddingVertical: 10,
        borderRadius: 20
    },
    useText: {
        color: '#fff',
        fontSize: 16
    },
    stepHeader: {
        paddingHorizontal: 20,
        paddingBottom: 10,
    },
    stepTitle: {
        fontSize: 16,
        fontWeight: '600',
        color: '#000',
    },
    stepSubtitle: {
        marginTop: 4,
        fontSize: 12,
        color: '#666',
    },
    stepRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        paddingHorizontal: 20,
        paddingBottom: 10,
        gap: 8,
    },
    stepItem: {
        alignItems: 'center',
        flex: 1,
        paddingVertical: 6,
        borderRadius: 8,
        backgroundColor: '#F5F5F5',
    },
    stepItemActive: {
        backgroundColor: '#EDEDED',
        borderWidth: 1,
        borderColor: '#DB3022',
    },
    stepThumbnail: {
        width: 44,
        height: 44,
        borderRadius: 6,
        marginBottom: 4,
    },
    stepPlaceholder: {
        width: 44,
        height: 44,
        borderRadius: 6,
        backgroundColor: '#D9D9D9',
        marginBottom: 4,
    },
    stepLabel: {
        fontSize: 11,
        color: '#333',
    },
    thumbnailContainer: {
        position: 'relative',
    },
    removeIconContainer: {
        position: 'absolute',
        top: -8,
        right: -8,
        backgroundColor: '#DB3022',
        width: 18,
        height: 18,
        borderRadius: 9,
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: 10,
    },
    removeIconText: {
        color: '#fff',
        fontSize: 10,
        fontWeight: 'bold',
    },
    stepItemSwapping: {
        backgroundColor: '#FFE5E5',
        borderWidth: 2,
        borderColor: '#DB3022',
        borderStyle: 'dashed',
    },
    swapBanner: {
        backgroundColor: '#DB3022',
        paddingVertical: 6,
        alignItems: 'center',
    },
    swapText: {
        color: '#fff',
        fontSize: 12,
        fontWeight: '500',
    },
    leftControls: {
        flexDirection: 'row',
        gap: 10,
    },
    uploadButton: {
        borderColor: '#fff',
        borderWidth: 1,
        paddingHorizontal: 15,
        paddingVertical: 10,
        borderRadius: 20
    },
});
