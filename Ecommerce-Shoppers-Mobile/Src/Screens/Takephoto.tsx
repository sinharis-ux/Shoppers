import React, { useEffect, useState } from 'react';
import { StyleSheet, Text, View, Image, TouchableOpacity, StatusBar, ImageBackground, Alert, ActivityIndicator } from 'react-native';
import { Images } from '../Assets/index';
import { useNavigation, NavigationProp } from '@react-navigation/native';
import { launchImageLibrary, ImageLibraryOptions, Asset } from 'react-native-image-picker';
import { postRequest } from '../Network/apiClient';
import { ApiConstants } from '../Theme/ApiConstants';
import AsyncStorage from '@react-native-async-storage/async-storage';

interface ImagePickerResponse {
  didCancel?: boolean;
  errorCode?: string;
  errorMessage?: string;
  assets?: Asset[];
}

const STORAGE_KEYS = {
  SESSION_ID: '@app:session_id',
  SESSION_DATA: '@app:session_data',
};

const Takephoto = ({ navigation }: any) => {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const initialize = async () => {
      console.log("🔧 Initializing Takephoto component...");
      const existingSession = await checkExistingSession();

      if (!existingSession) {
        console.log("🆕 No existing session, creating new one...");
        await createNewSession();
      } else {
        console.log("✅ Using existing session");
      }
    };

    initialize();
  }, []);

  const checkExistingSession = async () => {
    try {
      const savedSessionId = await AsyncStorage.getItem(STORAGE_KEYS.SESSION_ID);
      if (savedSessionId) {
        setSessionId(savedSessionId);
        console.log("📱 Found existing session:", savedSessionId);
        return savedSessionId;
      }
      console.log("📱 No existing session found");
      return null;
    } catch (storageError) {
      console.error("Error reading session from storage:", storageError);
      return null;
    }
  };

  const saveSession = async (id: string) => {
    try {
      await AsyncStorage.setItem(STORAGE_KEYS.SESSION_ID, id);
      setSessionId(id);
      console.log("💾 Session saved to storage:", id);
    } catch (storageError) {
      console.error("Error saving session:", storageError);
    }
  };

  const createNewSession = async (): Promise<string | null> => {
    setError(null);
    setLoading(true);

    try {
      console.log("🚀 Creating new session...");
      const response = await postRequest(ApiConstants.CREATE_SESSION, {});

      console.log("📦 Full API Response:", JSON.stringify(response));

      if (response.success) {
        console.log("HTTP Status in createNewSession:", response.status);
        console.log("API Data createNewSession:", response.data);

        if (response.data?.status === 'success') {
          let sessionId: string | undefined;

          if (response.data?.session?.session_id) {
            sessionId = response.data.session.session_id;
            console.log("📝 Found session ID in data.session.session_id");
          }

          if (sessionId) {
            await saveSession(sessionId);
            console.log("🎉 Session created and saved:", sessionId);
            setLoading(false);
            return sessionId;
          }
        } else {
          console.log("❌ API returned unsuccessful status in response body");
          setError("Failed to create session. Please try again.");
        }
      } else {
        console.log("❌ HTTP request failed");
        setError("Network error. Please check your connection.");
      }
    } catch (error: any) {
      const errorMsg = error.message || "Unable to create session";
      setError(errorMsg);
      console.error("💥 Session creation error:", error);

      if (error.message !== "Session ID not found in response") {
        Alert.alert(
          "Connection Error",
          "Unable to connect to server. You can continue in offline mode.",
          [{ text: "OK" }]
        );
      }
    } finally {
      setLoading(false);
    }

    return null;
  };

  const handleTakePhoto = async () => {
    console.log("📸 Take photo clicked");

    let currentSessionId = sessionId;

    if (!currentSessionId) {
      console.log("🆕 No session ID, creating new one...");
      setLoading(true);
      currentSessionId = await createNewSession();
      if (!currentSessionId) {
        Alert.alert("Error", "Failed to create session. Please try again.");
        return;
      }
    }

    console.log("🎬 Navigating to Phototaken with session:", currentSessionId);
    navigation.navigate('Phototaken', {
      sessionId: currentSessionId
    });
  };

  const handleUploadImage = async () => {
    console.log("📁 Upload image clicked");

    let currentSessionId = sessionId;

    if (!currentSessionId) {
      console.log("🆕 No session ID, creating new one...");
      setLoading(true);
      currentSessionId = await createNewSession();
      if (!currentSessionId) {
        Alert.alert("Error", "Failed to create session. Please try again.");
        return;
      }
    }

    const options: ImageLibraryOptions = {
      mediaType: 'photo',
      quality: 0.8,
      maxWidth: 1536,
      maxHeight: 1536,
      selectionLimit: 4,
    };

    console.log("🖼️ Launching image library with session:", currentSessionId);
    launchImageLibrary(options, (response: ImagePickerResponse) => {
      if (response.didCancel) {
        console.log("👤 User cancelled image picker");
      } else if (response.errorCode) {
        console.log("❌ Image picker error:", response.errorMessage);
        Alert.alert("Error", "Failed to pick image. Please try again.");
      } else if (response.assets && response.assets.length > 0) {
        const selectedUris = response.assets
          .map(asset => asset.uri)
          .filter((uri): uri is string => Boolean(uri));

        if (selectedUris.length > 0) {
          const selectedImageMap = {
            front: selectedUris[0],
            side: selectedUris[1],
            back: selectedUris[2],
            face: selectedUris[3],
          };
          console.log("✅ Images selected:", selectedUris);
          console.log("🎬 Navigating to Phototaken with session:", currentSessionId);
          navigation.navigate('Phototaken', {
            selectedImageUris: selectedUris,
            selectedImageMap,
            sessionId: currentSessionId
          });
        } else {
          console.log("❌ No URI in selected image");
          Alert.alert("Error", "Invalid image selected. Please try again.");
        }
      }
    });
  };


  const refreshSession = async () => {
    console.log("🔄 Refreshing session...");
    try {
      await AsyncStorage.removeItem(STORAGE_KEYS.SESSION_ID);
      setSessionId(null);
      await createNewSession();
    } catch (error) {
      console.error("Error refreshing session:", error);
    }
  };

  return (
    <View style={styles.safeArea}>
      <StatusBar barStyle="dark-content" backgroundColor="#fff" />

      <View style={styles.headerContainer}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Image
            source={Images.img_Chevron}
            style={styles.backIcon}
            resizeMode="contain"
          />
        </TouchableOpacity>

        <Text style={styles.mainTitle}>Visual search</Text>

        <TouchableOpacity onPress={refreshSession} disabled={loading}>
          <Text style={[styles.refreshText, loading && styles.disabledText]}>
            🔄
          </Text>
        </TouchableOpacity>
      </View>

      <View style={styles.mainContent}>
        <ImageBackground
          source={Images.img_background}
          style={styles.backgroundImage}
          resizeMode="cover"
        >
          <View style={styles.overlayContent}>
            {loading ? (
              <View style={styles.centerContainer}>
                <ActivityIndicator size="large" color="#fff" />
                <Text style={styles.loadingText}>Creating session...</Text>
              </View>
            ) : error ? (
              <View style={styles.centerContainer}>
                <Text style={styles.errorText}>{error}</Text>
                <TouchableOpacity
                  style={styles.retryButton}
                  onPress={createNewSession}
                >
                  <Text style={styles.retryButtonText}>Retry</Text>
                </TouchableOpacity>
              </View>
            ) : (
              <>
                <Text style={styles.description}>
                  Search for an outfit by{'\n'}taking a photo or uploading{'\n'}an image
                </Text>

                <View style={styles.buttonsWrapper}>
                  <TouchableOpacity
                    style={[styles.primaryButton, loading && styles.disabledButton]}
                    onPress={handleTakePhoto}
                    activeOpacity={0.8}
                    disabled={loading}
                  >
                    <Text style={styles.primaryButtonText}>
                      {loading ? "LOADING..." : "TAKE A PHOTO"}
                    </Text>
                  </TouchableOpacity>

                  <TouchableOpacity
                    style={[styles.secondaryButton, loading && styles.disabledButton]}
                    onPress={handleUploadImage}
                    activeOpacity={0.8}
                    disabled={loading}
                  >
                    <Text style={styles.secondaryButtonText}>
                      {loading ? "LOADING..." : "UPLOAD IMAGE"}
                    </Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[styles.primaryButton, loading && styles.disabledButton]}
                    onPress={() => {
                      navigation.navigate("Productlist")
                    }}
                    activeOpacity={0.8}
                    disabled={loading}
                  >
                    <Text style={styles.primaryButtonText}>
                      {"SEE PRODUCTS LIST"}
                    </Text>
                  </TouchableOpacity>
                </View>
              </>
            )}
          </View>
        </ImageBackground>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#fff'
  },
  headerContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 24,
    paddingTop: 50,
    paddingBottom: 10,
  },
  backIcon: {
    width: 16,
    height: 16
  },
  mainTitle: {
    fontSize: 19,
    fontWeight: '600',
    color: '#000',
    flex: 1,
    textAlign: 'center'
  },
  refreshText: {
    fontSize: 18,
    width: 30,
    textAlign: 'center',
  },
  disabledText: {
    opacity: 0.5,
  },
  mainContent: {
    flex: 1
  },
  backgroundImage: {
    flex: 1,
    width: '100%',
    height: '100%',
    justifyContent: 'center'
  },
  overlayContent: {
    flex: 1,
    justifyContent: 'center',
    width: '100%',
    paddingHorizontal: 24,
    paddingBottom: 60,
  },
  centerContainer: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  description: {
    fontSize: 28,
    color: '#fff',
    marginBottom: 25,
    fontWeight: '500',
    textAlign: 'center',
    lineHeight: 34,
  },
  buttonsWrapper: {
    width: '100%',
    alignItems: 'center',
    gap: 16
  },
  primaryButton: {
    width: '100%',
    maxWidth: 370,
    height: 56,
    backgroundColor: '#DB3022',
    justifyContent: 'center',
    alignItems: 'center',
    borderRadius: 27
  },
  secondaryButton: {
    width: '100%',
    maxWidth: 370,
    height: 56,
    justifyContent: 'center',
    alignItems: 'center',
    borderRadius: 27,
    borderWidth: 2,
    borderColor: '#fff'
  },
  disabledButton: {
    opacity: 0.6,
  },
  primaryButtonText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '600',
    letterSpacing: 0.5,
  },
  secondaryButtonText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '600',
    letterSpacing: 0.5,
  },
  loadingText: {
    color: '#fff',
    fontSize: 16,
    marginTop: 20,
    fontWeight: '500',
  },
  errorText: {
    color: '#fff',
    fontSize: 16,
    marginBottom: 20,
    textAlign: 'center',
    backgroundColor: 'rgba(219, 48, 34, 0.8)',
    padding: 15,
    borderRadius: 10,
  },
  retryButton: {
    backgroundColor: '#fff',
    paddingHorizontal: 30,
    paddingVertical: 12,
    borderRadius: 25,
  },
  retryButtonText: {
    color: '#DB3022',
    fontWeight: '600',
    fontSize: 14,
  },
  sessionInfo: {
    alignItems: 'center',
    marginBottom: 20,
    padding: 10,
    backgroundColor: 'rgba(255,255,255,0.1)',
    borderRadius: 10,
  },
  sessionText: {
    color: '#fff',
    fontSize: 12,
    fontFamily: 'monospace',
    marginBottom: 5,
  },
  sessionSubText: {
    color: '#ddd',
    fontSize: 10,
    fontFamily: 'monospace',
  },
});

export default Takephoto;