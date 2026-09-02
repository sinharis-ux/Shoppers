import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, ScrollView, StyleSheet, Image, TouchableOpacity, FlatList, ActivityIndicator, Pressable, Alert, StatusBar, Platform, PermissionsAndroid, NativeModules, TextInput, } from 'react-native';
import { Images } from '../Assets';
import { useNavigation, useRoute } from '@react-navigation/native';
import { ApiConstants } from '../Theme/ApiConstants';
import { getRequest } from '../Network/apiClient';
import AsyncStorage from '@react-native-async-storage/async-storage';
import axios from 'axios';
import { SafeAreaView } from 'react-native-safe-area-context';
import ReactNativeBlobUtil from 'react-native-blob-util';


const Productlist = () => {
    const navigation = useNavigation<any>();
    const route = useRoute<any>();

    const [loading, setLoading] = useState(true);
    const [products, setProducts] = useState<any[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [sessionId, setSessionId] = useState<string | null>(null);
    const [showAvatarModal, setShowAvatarModal] = useState(false);
    const [tryOnLoading, setTryOnLoading] = useState(false);
    const [avatarImageUrl, setAvatarImageUrl] = useState<string | null>(null);
    const [selectedProduct, setSelectedProduct] = useState<any>(null);
    const [selectedCategory, setSelectedCategory] = useState<
        'top' | 'bottom' | 'outfit' | null
    >(null);
    const [selectedFilter, setSelectedFilter] = useState('Men');
    const [searchQuery, setSearchQuery] = useState('');
    const [searchLoading, setSearchLoading] = useState(false);
    const [searchPage, setSearchPage] = useState(1);
    const [productPage, setProductPage] = useState(1);
    const [isSearchMode, setIsSearchMode] = useState(false);
    const [showSearchBar, setShowSearchBar] = useState(false);
    const [totalSearchCount, setTotalSearchCount] = useState(0);
    const scrollRef = React.useRef<ScrollView>(null);

    /* ---------------- SESSION ID ---------------- */
    useEffect(() => {
        if (route.params?.sessionId) {
            setSessionId(route.params.sessionId);
            AsyncStorage.setItem('@app:session_id', route.params.sessionId);
        } else {
            AsyncStorage.getItem('@app:session_id').then(id => {
                if (id) setSessionId(id);
            });
        }

    }, [route.params]);

    /* ---------------- FETCH PRODUCTS ---------------- */
    useEffect(() => {
        // If user has an active search query, re-run search with new category
        if (searchQuery.trim()) {
            searchProducts(searchQuery, 1); // Reset to page 1 when category changes
        } else {
            // Otherwise fetch regular products for the selected category
            fetchProducts(1);
        }
    }, [selectedFilter]);

    const fetchProducts = async (page: number = 1) => {
        setLoading(true);
        setIsSearchMode(false);
        try {
            const response = await getRequest(ApiConstants.GET_PRODUCTS, { 
                category: selectedFilter,
                page: page
            });
            if (response?.success) {
                setProducts(response.data?.results || []);
                setProductPage(page);
            } else {
                setError('Failed to load products');
            }
        } catch {
            setError('Network error');
        }
        setLoading(false);
    };

    /* ---------------- SEARCH PRODUCTS ---------------- */
    const searchProducts = async (query: string, page: number = 1) => {
        if (!query.trim()) return;
        setSearchLoading(true);
        setIsSearchMode(true);
        setError(null);
        try {
            const searchParams = {
                query: query.trim(),
                category: selectedFilter, // Add selected category (Men/Women/Children)
                page
            };
            console.log('🔍 Searching with params:', searchParams);
            
            // Using getRequest which automatically handles formatting and base URLs safely
            const response = await getRequest(ApiConstants.SEARCH_PRODUCTS, searchParams);
            
            if (response?.success) {
                const data = response.data;
                if (data?.results) {
                    setProducts(data.results);
                    setTotalSearchCount(data.count || data.results.length);
                } else if (Array.isArray(data)) {
                    setProducts(data);
                    setTotalSearchCount(data.length);
                } else {
                    setProducts([]);
                    setTotalSearchCount(0);
                }
                setSearchPage(page);
                scrollRef.current?.scrollTo({ y: 0, animated: true });
            } else {
                // Display the actual server error message (e.g. "It only supports cloths searching.")
                setError(response.message || 'Search failed. Please try again.');
            }
        } catch (e) {
            console.log('Search error:', e);
            setError('Search failed. Please try again.');
        } finally {
            setSearchLoading(false);
        }
    };

    const handleSearch = () => {
        if (searchQuery.trim()) {
            setSearchPage(1);
            searchProducts(searchQuery, 1);
        }
    };

    const goToNextPage = () => {
        if (isSearchMode) {
            const nextPage = searchPage + 1;
            searchProducts(searchQuery, nextPage);
        } else {
            const nextPage = productPage + 1;
            fetchProducts(nextPage);
        }
    };

    const goToPrevPage = () => {
        if (isSearchMode) {
            if (searchPage > 1) {
                const prevPage = searchPage - 1;
                searchProducts(searchQuery, prevPage);
            }
        } else {
            if (productPage > 1) {
                const prevPage = productPage - 1;
                fetchProducts(prevPage);
            }
        }
    };

    const clearSearch = () => {
        setSearchQuery('');
        setIsSearchMode(false);
        setShowSearchBar(false);
        setSearchPage(1);
        setProductPage(1);
        setTotalSearchCount(0);
        fetchProducts(1);
    };

    const downloadAndSaveImage = async (imageUrl: string) => {
        try {
            if (Platform.OS === 'android') {
                const permission =
                    Platform.Version >= 33
                        ? PermissionsAndroid.PERMISSIONS.READ_MEDIA_IMAGES
                        : PermissionsAndroid.PERMISSIONS.WRITE_EXTERNAL_STORAGE;

                const granted = await PermissionsAndroid.request(permission);
                if (granted !== PermissionsAndroid.RESULTS.GRANTED) {
                    Alert.alert('Permission denied');
                    return;
                }
            }

            const { config } = ReactNativeBlobUtil;
            const fileName = `IMG_${Date.now()}.jpg`;

            await config({
                fileCache: true,
                addAndroidDownloads: {
                    useDownloadManager: true,
                    notification: true,
                    title: fileName,
                    description: 'Downloading image',
                    mime: 'image/jpeg',
                    mediaScannable: true,
                    storeInDownloads: true,
                },
            }).fetch('GET', imageUrl);

            Alert.alert('Success', 'Image saved to gallery');
        } catch (e) {
            console.log(e);
            Alert.alert('Error', 'Failed to save image');
        }
    };


  
    /* ---------------- OPEN MODAL ---------------- */
    const openTryOnModal = (product: any) => {
        if (!sessionId) {
            Alert.alert('Session Missing', 'Session not found');
            return;
        }
        setSelectedProduct(product);
        setSelectedCategory(null);
        setAvatarImageUrl(null);
        setShowAvatarModal(true);
    };

    /* ---------------- TRY ON API ---------------- */
    const startTryOn = async (category: 'top' | 'bottom' | 'outfit') => {
        if (!selectedProduct || !sessionId) return;
        console.log("selectedProduct", selectedProduct);


        setTryOnLoading(true);
        setSelectedCategory(category);

        try {
            const productId = selectedProduct.product_id || selectedProduct.asin

            const formData = new FormData();
            formData.append('product_id', productId);
            formData.append('session_id', sessionId);
            formData.append('garment_category', category);

            console.log("formData in startTryOn:", formData);


            const response = await axios.post(
                `${ApiConstants.BASE_URL}virtual-tryon/`,
                formData,
                {
                    headers: {
                        Accept: 'application/json',
                        'Content-Type': 'multipart/form-data',
                    },
                }
            );

            const data = response.data;
            console.log("data in startTryOn:", data);


            if (data?.status === 'success' && data?.tryon_url) {
                setAvatarImageUrl(
                    `${ApiConstants.IMAGE_URL}${data.tryon_url}`
                );
            } else {
                Alert.alert('Try-On Failed');
                setShowAvatarModal(false);
            }
        } catch (e) {
            Alert.alert('Error', 'Try-on failed');
            setShowAvatarModal(false);
        } finally {
            setTryOnLoading(false);
        }
    };

    /* ---------------- PRODUCT CARD ---------------- */
    const ProductCard = ({ item }: any) => (
        <Pressable
            style={styles.productCard}
            onPress={() => openTryOnModal(item)}
        >
            <Image
                source={{ uri: item.image_url }}
                style={styles.productImage}
                resizeMode="contain"
            />
            <Text numberOfLines={2} style={styles.productTitle}>
                {item.title}
            </Text>
            <Text style={styles.currentPrice}>{item.price}</Text>
        </Pressable>
    );

    /* ---------------- LOADING ---------------- */
    if (loading) {
        return (
            <View style={styles.center}>
                <ActivityIndicator size="large" />
            </View>
        );
    }

    /* ---------------- ERROR ---------------- */
    if (error) {
        return (
            <View style={styles.center}>
                <Text>{error}</Text>
            </View>
        );
    }

    console.log("avatarImageUrl:", avatarImageUrl)

    /* ---------------- UI ---------------- */
    return (
        <SafeAreaView style={styles.screen}>
            <StatusBar barStyle="dark-content" backgroundColor="#FAF9F6" />

            {/* TRY ON MODAL */}
            {showAvatarModal && (
                <View style={styles.modalOverlay}>
                    <View style={styles.modalBox}>
                        <Text style={styles.modalTitle}>
                            Select Try-On Type
                        </Text>

                        {!selectedCategory && (
                            <>
                                <View style={styles.optionRow}>
                                    <TouchableOpacity
                                        style={styles.optionButton}
                                        onPress={() =>
                                            startTryOn('top')
                                        }
                                    >
                                        <Text style={styles.optionText}>
                                            Top
                                        </Text>
                                    </TouchableOpacity>

                                    <TouchableOpacity
                                        style={styles.optionButton}
                                        onPress={() =>
                                            startTryOn('bottom')
                                        }
                                    >
                                        <Text style={styles.optionText}>
                                            Bottom
                                        </Text>
                                    </TouchableOpacity>
                                </View>
                                <TouchableOpacity
                                    style={[styles.optionButton, styles.optionButtonFull]}
                                    onPress={() => startTryOn('outfit')}
                                >
                                    <Text style={styles.optionText}>
                                        Outfit
                                    </Text>
                                </TouchableOpacity>
                            </>
                        )}

                        {tryOnLoading && (
                            <ActivityIndicator
                                size="large"
                                color="#9B6359"
                            />
                        )}

                        {!tryOnLoading && avatarImageUrl && (
                            <Image
                                source={{ uri: avatarImageUrl }}
                                style={styles.avatarImage}
                                resizeMode="contain"
                            />
                        )}

                        <TouchableOpacity
                            style={[styles.closeButton, { marginBottom: 12 }]}
                            onPress={() => setShowAvatarModal(false)}
                        >
                            <Text style={styles.closeButtonText}>
                                Close
                            </Text>
                        </TouchableOpacity>
                        {avatarImageUrl &&
                            <TouchableOpacity
                                style={styles.closeButton}
                                onPress={() => downloadAndSaveImage(avatarImageUrl)}
                            >
                                <Text style={styles.closeButtonText}>
                                    Download
                                </Text>
                            </TouchableOpacity>}
                    </View>
                </View>
            )}

            <ScrollView ref={scrollRef}>
                <View style={styles.header}>
                    <TouchableOpacity onPress={() => navigation.goBack()}>
                        <Image source={Images.img_Chevron} />
                    </TouchableOpacity>
                    <Text style={styles.headerTitle}>
                        Products ({products.length})
                    </Text>
                    <TouchableOpacity onPress={() => setShowSearchBar(!showSearchBar)}>
                        <Image source={Images.img_search} />
                    </TouchableOpacity>
                </View>

                {/* SEARCH BAR */}
                {showSearchBar && (
                    <View style={styles.searchContainer}>
                        <View style={styles.searchInputWrapper}>
                            <Image source={Images.img_search} style={styles.searchIcon} />
                            <TextInput
                                style={styles.searchInput}
                                placeholder="Search products..."
                                placeholderTextColor="#999"
                                value={searchQuery}
                                onChangeText={setSearchQuery}
                                onSubmitEditing={handleSearch}
                                returnKeyType="search"
                                autoFocus
                            />
                            {searchQuery.length > 0 && (
                                <TouchableOpacity onPress={clearSearch}>
                                    <Text style={styles.clearText}>✕</Text>
                                </TouchableOpacity>
                            )}
                        </View>
                        <TouchableOpacity
                            style={styles.searchButton}
                            onPress={handleSearch}
                            disabled={searchLoading}
                        >
                            {searchLoading ? (
                                <ActivityIndicator size="small" color="#fff" />
                            ) : (
                                <Text style={styles.searchButtonText}>Search</Text>
                            )}
                        </TouchableOpacity>
                    </View>
                )}

                {/* Filter Buttons */}
                <View style={styles.filterContainer}>
                    {['Men', 'Women', 'Children'].map((category) => (
                        <TouchableOpacity
                            key={category}
                            style={[
                                styles.filterButton,
                                selectedFilter === category && styles.activeFilterButton,
                            ]}
                            onPress={() => setSelectedFilter(category)}
                        >
                            <Text
                                style={[
                                    styles.filterText,
                                    selectedFilter === category && styles.activeFilterText,
                                ]}
                            >
                                {category}
                            </Text>
                        </TouchableOpacity>
                    ))}
                </View>

                {loading ? (
                    <View style={styles.center}>
                        <ActivityIndicator size="large" />
                    </View>
                ) : (
                    <FlatList
                        data={products}
                        numColumns={2}
                        keyExtractor={(item, index) =>
                            `${item.id || index}`
                        }
                        scrollEnabled={false}
                        columnWrapperStyle={{
                            justifyContent: 'space-between',
                        }}
                        contentContainerStyle={{ padding: 10 }}
                        renderItem={({ item }) => (
                            <View style={{ width: '48%' }}>
                                <ProductCard item={item} />
                            </View>
                        )}
                        ListEmptyComponent={
                            !loading && (
                                <View style={styles.center}>
                                    <Text>No products found</Text>
                                </View>
                            )
                        }
                    />
                )}

                {/* PAGINATION */}
                {products.length > 0 && (
                    <View style={styles.paginationContainer}>
                        <TouchableOpacity
                            style={[
                                styles.pageButton,
                                (isSearchMode ? searchPage <= 1 : productPage <= 1) && styles.pageButtonDisabled,
                            ]}
                            onPress={goToPrevPage}
                            disabled={isSearchMode ? (searchPage <= 1 || searchLoading) : (productPage <= 1 || loading)}
                        >
                            <Text
                                style={[
                                    styles.pageButtonText,
                                    (isSearchMode ? searchPage <= 1 : productPage <= 1) && styles.pageButtonTextDisabled,
                                ]}
                            >
                                ← Previous
                            </Text>
                        </TouchableOpacity>

                        <Text style={styles.pageInfo}>Page {isSearchMode ? searchPage : productPage}</Text>

                        <TouchableOpacity
                            style={styles.pageButton}
                            onPress={goToNextPage}
                            disabled={isSearchMode ? searchLoading : loading}
                        >
                            {isSearchMode ? (
                                searchLoading ? (
                                    <ActivityIndicator size="small" color="#fff" />
                                ) : (
                                    <Text style={styles.pageButtonText}>Next →</Text>
                                )
                            ) : (
                                loading ? (
                                    <ActivityIndicator size="small" color="#fff" />
                                ) : (
                                    <Text style={styles.pageButtonText}>Next →</Text>
                                )
                            )}
                        </TouchableOpacity>
                    </View>
                )}
            </ScrollView>
        </SafeAreaView>
    );
};

export default Productlist;

/* ---------------- STYLES ---------------- */
const styles = StyleSheet.create({
    screen: { flex: 1, backgroundColor: '#FAF9F6' },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center' },

    header: {
        padding: 16,
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
    },
    headerTitle: { fontSize: 18, fontWeight: '600' },

    // Search bar styles
    searchContainer: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: 12,
        paddingBottom: 10,
        backgroundColor: '#FAF9F6',
    },
    searchInputWrapper: {
        flex: 1,
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: '#fff',
        borderRadius: 10,
        borderWidth: 1,
        borderColor: '#ddd',
        paddingHorizontal: 10,
        height: 44,
    },
    searchIcon: {
        width: 18,
        height: 18,
        tintColor: '#999',
        marginRight: 8,
    },
    searchInput: {
        flex: 1,
        fontSize: 15,
        color: '#333',
        paddingVertical: 0,
    },
    clearText: {
        fontSize: 16,
        color: '#999',
        paddingHorizontal: 6,
    },
    searchButton: {
        backgroundColor: '#9B6359',
        borderRadius: 10,
        paddingHorizontal: 16,
        height: 44,
        justifyContent: 'center',
        alignItems: 'center',
        marginLeft: 8,
    },
    searchButtonText: {
        color: '#fff',
        fontWeight: '600',
        fontSize: 14,
    },

    // Pagination styles
    paginationContainer: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingHorizontal: 16,
        paddingVertical: 14,
        backgroundColor: '#fff',
        marginHorizontal: 10,
        marginBottom: 16,
        borderRadius: 10,
    },
    pageButton: {
        backgroundColor: '#9B6359',
        paddingVertical: 10,
        paddingHorizontal: 18,
        borderRadius: 8,
    },
    pageButtonDisabled: {
        backgroundColor: '#ddd',
    },
    pageButtonText: {
        color: '#fff',
        fontWeight: '600',
        fontSize: 14,
    },
    pageButtonTextDisabled: {
        color: '#999',
    },
    pageInfo: {
        fontSize: 15,
        fontWeight: '600',
        color: '#333',
    },

    productCard: {
        backgroundColor: '#fff',
        borderRadius: 10,
        padding: 10,
        marginBottom: 12,
    },
    productImage: { width: '100%', height: 200 },
    productTitle: { fontSize: 14, fontWeight: '600' },
    currentPrice: { fontSize: 14, fontWeight: '700' },

    modalOverlay: {
        ...StyleSheet.absoluteFillObject,
        backgroundColor: 'rgba(0,0,0,0.7)',
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: 20,
    },
    modalBox: {
        width: '90%',
        backgroundColor: '#fff',
        borderRadius: 12,
        padding: 16,
    },
    modalTitle: {
        fontSize: 18,
        fontWeight: '600',
        textAlign: 'center',
        marginBottom: 12,
    },
    optionRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        marginBottom: 16,
    },
    optionButton: {
        flex: 1,
        backgroundColor: '#9B6359',
        padding: 14,
        borderRadius: 8,
        marginHorizontal: 6,
        alignItems: 'center',
    },
    optionButtonFull: {
        flex: undefined,
        marginHorizontal: 0,
        marginTop: 8,
    },
    optionText: {
        color: '#fff',
        fontWeight: '600',
    },
    avatarImage: {
        width: '100%',
        height: 400,
        marginTop: 10,
    },
    closeButton: {
        marginTop: 12,
        backgroundColor: '#9B6359',
        padding: 12,
        borderRadius: 8,
        alignItems: 'center',
    },
    closeButtonText: {
        color: '#fff',
        fontWeight: '600',
    },
    filterContainer: {
        flexDirection: 'row',
        justifyContent: 'center',
        paddingVertical: 10,
        backgroundColor: '#fff',
    },
    filterButton: {
        paddingVertical: 8,
        paddingHorizontal: 16,
        borderRadius: 20,
        marginHorizontal: 5,
        backgroundColor: '#f0f0f0',
        borderWidth: 1,
        borderColor: '#ddd',
    },
    activeFilterButton: {
        backgroundColor: '#9B6359',
        borderColor: '#9B6359',
    },
    filterText: {
        fontSize: 14,
        color: '#333',
        fontWeight: '500',
    },
    activeFilterText: {
        color: '#fff',
        fontWeight: '600',
    },
});
