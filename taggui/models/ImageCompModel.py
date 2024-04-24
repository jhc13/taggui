import cv2
import hashlib
import numpy as np

class ImageComparator:
    def __init__(self, imagepath):
        self.baseline = imagepath
        pass

    def hash_comparison(self, img_path2):
        hash1 = self._compute_hash(self.baseline)
        hash2 = self._compute_hash(img_path2)
        return hash1 == hash2

    def _compute_hash(self, img_path):
        with open(img_path, 'rb') as f:
            img_data = f.read()
            return hashlib.md5(img_data).hexdigest()

    def short_comparison(self, img_path2):
        img1 = cv2.imread(self.baseline)
        img2 = cv2.imread(img_path2)
        avg_color1 = np.mean(img1, axis=(0, 1))
        avg_color2 = np.mean(img2, axis=(0, 1))
        return np.array_equal(avg_color1, avg_color2)

    def histogram_comparison(self, img_path2):
        img1 = cv2.imread(self.baseline)
        img2 = cv2.imread(img_path2)
        hist1 = cv2.calcHist([img1], [0, 1, 2], None, [256, 256, 256], [0, 256, 0, 256, 0, 256])
        hist2 = cv2.calcHist([img2], [0, 1, 2], None, [256, 256, 256], [0, 256, 0, 256, 0, 256])
        return cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)

    def template_matching(self, img_path2):
        img1 = cv2.imread(self.baseline, 0)
        img2 = cv2.imread(img_path2, 0)
        res = cv2.matchTemplate(img1, img2, cv2.TM_CCOEFF_NORMED)
        _, similarity = cv2.minMaxLoc(res)
        return similarity

    def feature_matching(self, img_path2):
        sift = cv2.SIFT_create()
        img1 = cv2.imread(self.baseline, 0)
        img2 = cv2.imread(img_path2, 0)
        kp1, des1 = sift.detectAndCompute(img1, None)
        kp2, des2 = sift.detectAndCompute(img2, None)
        bf = cv2.BFMatcher()
        matches = bf.knnMatch(des1, des2, k=2)
        good_matches = []
        for m, n in matches:
            if m.distance < 0.75 * n.distance:
                good_matches.append([m])
        return len(good_matches)

    def pixel_comparison(self, img_path2):
        img1 = cv2.imread(self.baseline)
        img2 = cv2.imread(img_path2)
        return np.array_equal(img1, img2)
