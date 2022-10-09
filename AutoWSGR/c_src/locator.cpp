#include <opencv2/opencv.hpp>
#include "module/image_function.h"

using namespace std;
using cv::Mat;
using cv::imread;
using cv::imwrite;
using cv::imshow;
using cv::waitKey;
/*compile:
	current path: ./c_src
	general:
		g++.exe -std=c++17 -O3 locator.cpp -o locator.exe -I {your_opencv_include} -L {your_opencv_lib} -l libopencv_core454 -l libopencv_imgcodecs454 
	for me(huan_yp):
		g++.exe -std=c++17 -O3 locator.cpp -o locator.exe -I H:/opencv/opencv-4.5.4mingw/include -L H:/opencv/opencv-4.5.4mingw/lib -l libopencv_core454 -l libopencv_imgcodecs454 
*/
/*function:
	locate the blue textbox and write other pixel (255,255,255)
*/
const int MAX_HEIGHT = 1000, MAX_WIDTH = 2000;
const int KEY_COLOR_COUNT = 3;
const vector<vector<int>> BGR_COLOR({{162, 98, 18}, {173, 103, 17}, {196, 116, 16}});

bool is_key[MAX_HEIGHT + 5][MAX_WIDTH + 5];
bool is_line_legal[MAX_HEIGHT + 5];

bool cmp_line(const vector<pair<int,int>> &l1, const vector<pair<int,int>> &l2){
	for(auto s1:l1){
		bool flag = false;
		for(auto s2:l2)if(min(abs(s1.first-s1.first), abs(s1.second-s2.second)) <= 2){
			flag = true;
			break;
		}
		if(!flag)
			return false;
	}
	return true;
}

string merge(char* a,const char* b){
	char ch[1000];
	strcpy(ch, a);
	strcat(ch, b);
	return ch;
}
int main(int argc,char **args){
//	printf("%d\n", is_key_color(vector<uchar>({123, 123, 123}), BGR_COLOR, 20, 3));
	char* ROOT = args[1];
	ofstream out(merge(ROOT,"/res.out"));
	ifstream in_stream(merge(ROOT, "/locator.in"));
	string image_path;
	in_stream >> image_path;
//	cout << image_path;
	Mat image = imread(image_path);
	if(image.empty()){
		printf("Image is empty!!!,Please check the path:%s", image_path.data());
		out << "Image is empty!!!,Please check the path:" << image_path;
		exit(0);
	}
//	imshow("source_image", image);
//	waitKey(0);
//	uchar* ptr = image.ptr<uchar>(0);
//	printf("%d %d %d\n", *ptr, *(ptr + 1), *(ptr + 2));
//	uchar* ptr = image.ptr<uchar>(0);
	for(int i=0;i<image.rows;i++){
		uchar* ptr = image.ptr<uchar>(i);
		for(int j=0;j<image.cols;j++){
		
			is_key[i][j] = is_key_color(ptr, BGR_COLOR, 20.0, 3);
			
			ptr += 3;
		}	
	}
	int n = image.rows, m = image.cols;
	vector<pair<int,int>> segments[MAX_HEIGHT];
	for(int i=1;i<n;i++){
		int last_key = -1;
		for(int j=1;j<m;j++){
			if(is_key[i][j]){
				if(!is_key[i][j-1])
					last_key = j;
			}
			else{
				if(is_key[i][j-1] && j - last_key > 10)
					segments[i].emplace_back(last_key, j-1);
			}
		}
	}
	for(int i=1;i<n;i++){
		if(segments[i].empty()){
			continue;
		}
		int cnt1=0,cnt2=0;
		for(int j=-8;j<=-1;j++)if(i + j > 0 && i + j < n)
			cnt1 += cmp_line(segments[i], segments[i + j]);
		
		for(int j=1;j<=8;j++)if(i + j > 0 && i + j < n)
			cnt2 += cmp_line(segments[i], segments[i + j]);
		
		if(max(cnt1, cnt2) >= 6)
			is_line_legal[i] = true; 
		
	}
	vector<pair<int,int>> lines;
	int lst = -1;
	for(int i=0;i<n;i++){
		if(!is_line_legal[i]){
			if(lst != -1){
				lines.emplace_back(lst, i);
				lst = -1;
			}
			memset(image.ptr<uchar>(i), 255, (m) * 3);
		}
		else{
			if(lst == -1)
				lst = i;
		}
	}

	
	out << lines.size() << endl;
	for(auto v:lines)
	out << v.first << ' ' << v.second << endl;
	imwrite("1.PNG", image);
//	imshow("image", image);
//	waitKey();
	return 0;
}
