#include <opencv2/opencv.hpp>
#include "module/image_function.h"

using namespace std;
using cv::Mat;
using cv::imread;
using cv::imwrite;
using cv::imshow;
using cv::waitKey;

/*function:
	locate the blue textbox and write other pixel (255,255,255)
*/
const int MAX_HEIGHT = 540, MAX_WIDTH = 960;
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

int main(int argc,char **args){
//	printf("%d\n", is_key_color(vector<uchar>({123, 123, 123}), BGR_COLOR, 20, 3));
	ifstream in_stream("locator.in");
	string image_path;
	in_stream >> image_path;
//	cout << image_path;
	Mat image = imread(image_path);
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
	for(int i=0;i<n;i++){
		if(!is_line_legal[i])
			memset(image.ptr<uchar>(i), 255, (m) * 3);
		else{
			for(int j=0;j<m;j++)if(!is_key[i][j]){
			//	uchar* ptr = image.ptr<uchar>(i, j);
			//	if(*min_element(ptr, ptr+3) >= 200)
			//		memset(ptr, 255, 3);
			//	else{
				//	memcpy(ptr, &BGR_COLOR[2][0], 3);
			//		ptr[0] = min(ptr[0] + 25, 255);
			//		ptr[1] = min(ptr[1] + 25, 255);
			//		ptr[2] = min(ptr[2] + 25, 255);
			//	}
			}
		}
	}
	imwrite("1.PNG", image);
	imshow("image", image);
	waitKey();
	return 0;
}