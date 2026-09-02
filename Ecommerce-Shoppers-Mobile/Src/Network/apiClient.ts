// import axios, { AxiosResponse } from "axios";
// import { ApiConstants } from "../Theme/ApiConstants";

// const api = axios.create({
//   baseURL: ApiConstants.BASE_URL,
//   timeout: 10000,
//   headers: {
//     "Content-Type": "application/json",
//   },
//   // ✅ Always treat all HTTP codes as valid responses
//   validateStatus: () => true,
// });

// // Request interceptor
// api.interceptors.request.use(
//   async (config: any) => {
//     try {
//       if (config.data instanceof FormData) {
//         config.headers["Content-Type"] = "multipart/form-data";
//       }

//       return config;
//     } catch (error) {
//       console.error("Error in request interceptor:", error);
//       return config;
//     }
//   },
//   (error: any) => Promise.reject(error)
// );



// // ✅ Response interceptor: normalize all responses

// api.interceptors.response.use(
//   (response: AxiosResponse) => {
//     // Success response (server returned anything)
//     const data = response.data;
//     console.log("data in apiclient file:",data);
    

//     // Try to extract meaningful message
//     let message =
//       data?.errors?.email?.[0] ||
//       data?.errors?.password?.[0] ||
//       data?.message ||
//       "Something went wrong, Please try again later";

//     return {
//       ...response,
//       message,
//       error: false,
//     };
//   },
//   (error: any) => {
//     // Network error or server did not respond
//     const status = error.response?.status || 0; // 0 means network error
//     const data = error.response?.data || {};

//     let message = "Something went wrong, Please try again later";

//     if (status === 0) {
//       // Network error
//       message = "No internet connection. Please check your network.";
//     }
//     else if (status == 500){
//        message = "Something went wrong at our server, Please try again later";
//     }
//     else {
//       // Server responded with error
//       message =
//         data?.errors?.email?.[0] ||
//         data?.errors?.password?.[0] ||
//         data?.message ||
//         message;
//     }

//     return Promise.resolve({
//       status,
//       data,
//       error: true,
//       message,
//     });
//   }
// );



// export interface ApiResponse<T = any> extends AxiosResponse<T> {
//   message: string;
//   error?: boolean;
// }

// // Common GET method
// export const getRequest = async (url: string, params?: object): Promise<ApiResponse> => {
//   return await api.get(url, { params });
// };

// // Common POST method
// export const postRequest = async (url: string, body?: object): Promise<ApiResponse> => {
//   return await api.post(url, body);
// };


// // Common PUT method
// export const putRequest = async (url: string, body?: object): Promise<ApiResponse> => {
//   return await api.put(url, body);
// };

// // Common DELETE method
// export const deleteRequest = async (url: string): Promise<ApiResponse> => {
//   return await api.delete(url);
// };

// // Common PATCH method
// export const patchRequest = async (url: string, body?: object): Promise<ApiResponse> => {
//   return await api.patch(url, body);
// };


// export default api;



// Network/apiClient.ts
import axios, { AxiosInstance, AxiosRequestConfig, AxiosResponse } from "axios";
import { ApiConstants } from "../Theme/ApiConstants";

// Types
export interface ApiResponse<T = any> {
  success: boolean;
  data?: T;
  message?: string;
  status: number;
  error?: boolean;
}

export interface ApiError {
  message: string;
  status: number;
  data?: any;
}

// Create axios instance
const api: AxiosInstance = axios.create({
  baseURL: ApiConstants.BASE_URL,
  timeout: 10000,
  headers: {
    "Content-Type": "application/json",
  },
});

// Request interceptor
api.interceptors.request.use(
  (config: AxiosRequestConfig) => {
    // You can add auth tokens here if needed
    // const token = await AsyncStorage.getItem('token');
    // if (token) {
    //   config.headers.Authorization = `Bearer ${token}`;
    // }
    
    // Handle FormData
    if (config.data instanceof FormData) {
      config.headers = {
        ...config.headers,
        "Content-Type": "multipart/form-data",
      };
    }
    
    console.log(`📤 ${config.method?.toUpperCase()} ${config.url}`);
    if (config.data && config.method !== 'get') {
      console.log("Request Data:", config.data);
    }
    
    return config;
  },
  (error) => {
    console.error("Request Error:", error);
    return Promise.reject(error);
  }
);

// Response interceptor
api.interceptors.response.use(
  (response: AxiosResponse) => {
    console.log(`📥 ${response.status} ${response.config.url}`);
    console.log("Response Data:", response.data);
    
    // Always return a consistent format
    return {
      success: true,
      data: response.data,
      message: response.data?.message || "Request successful",
      status: response.status,
      error: false,
    };
  },
  (error) => {
    console.error("Response Error:", error);
    
    // Handle different types of errors
    let errorMessage = "Something went wrong";
    let statusCode = 500;
    
    if (error.response) {
      // Server responded with error status
      statusCode = error.response.status;
      const serverData = error.response.data;
      
      errorMessage = 
        serverData?.message ||
        serverData?.error ||
        getErrorMessageFromStatus(statusCode);
        
    } else if (error.request) {
      // Request was made but no response received
      errorMessage = "No response from server. Check your internet connection.";
      statusCode = 0;
    } else {
      // Something else happened
      errorMessage = error.message || "Network error";
    }
    
    // Return consistent error format
    return Promise.resolve({
      success: false,
      data: error.response?.data || null,
      message: errorMessage,
      status: statusCode,
      error: true,
    });
  }
);

// Helper function for common error messages
const getErrorMessageFromStatus = (status: number): string => {
  switch (status) {
    case 400:
      return "Bad request. Please check your input.";
    case 401:
      return "Unauthorized. Please login again.";
    case 403:
      return "Forbidden. You don't have permission.";
    case 404:
      return "Resource not found.";
    case 409:
      return "Conflict. Resource already exists.";
    case 422:
      return "Validation failed.";
    case 429:
      return "Too many requests. Please try again later.";
    case 500:
      return "Internal server error. Please try again later.";
    case 502:
      return "Bad gateway. Server is down.";
    case 503:
      return "Service unavailable. Please try again later.";
    default:
      return "Something went wrong. Please try again.";
  }
};

// HTTP Methods with consistent return type
export const getRequest = async <T = any>(
  url: string, 
  params?: object,
  config?: AxiosRequestConfig
): Promise<ApiResponse<T>> => {
  try {
    const response = await api.get<T>(url, { params, ...config });
    return response as unknown as ApiResponse<T>;
  } catch (error) {
    return {
      success: false,
      status: 500,
      message: "Network request failed",
      error: true,
    };
  }
};

export const postRequest = async <T = any>(
  url: string, 
  data?: object,
  config?: AxiosRequestConfig
): Promise<ApiResponse<T>> => {
  try {
    const response = await api.post<T>(url, data, config);
    return response as unknown as ApiResponse<T>;
  } catch (error) {
    return {
      success: false,
      status: 500,
      message: "Network request failed",
      error: true,
    };
  }
};

export const putRequest = async <T = any>(
  url: string, 
  data?: object,
  config?: AxiosRequestConfig
): Promise<ApiResponse<T>> => {
  try {
    const response = await api.put<T>(url, data, config);
    return response as unknown as ApiResponse<T>;
  } catch (error) {
    return {
      success: false,
      status: 500,
      message: "Network request failed",
      error: true,
    };
  }
};

export const deleteRequest = async <T = any>(
  url: string,
  config?: AxiosRequestConfig
): Promise<ApiResponse<T>> => {
  try {
    const response = await api.delete<T>(url, config);
    return response as unknown as ApiResponse<T>;
  } catch (error) {
    return {
      success: false,
      status: 500,
      message: "Network request failed",
      error: true,
    };
  }
};

export const patchRequest = async <T = any>(
  url: string, 
  data?: object,
  config?: AxiosRequestConfig
): Promise<ApiResponse<T>> => {
  try {
    const response = await api.patch<T>(url, data, config);
    return response as unknown as ApiResponse<T>;
  } catch (error) {
    return {
      success: false,
      status: 500,
      message: "Network request failed",
      error: true,
    };
  }
};

// Upload file function
export const uploadFile = async <T = any>(
  url: string,
  fileUri: string,
  fieldName: string = "file",
  additionalData?: object
): Promise<ApiResponse<T>> => {
  try {
    const formData = new FormData();
    
    // @ts-ignore - React Native FormData
    formData.append(fieldName, {
      uri: fileUri,
      type: 'image/jpeg', // Adjust based on file type
      name: fileUri.split('/').pop() || 'photo.jpg',
    });
    
    // Add additional data if provided
    if (additionalData) {
      Object.keys(additionalData).forEach(key => {
        // @ts-ignore
        formData.append(key, additionalData[key]);
      });
    }
    
    const response = await api.post<T>(url, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    
    return response as unknown as ApiResponse<T>;
  } catch (error) {
    return {
      success: false,
      status: 500,
      message: "File upload failed",
      error: true,
    };
  }
};

export default api;