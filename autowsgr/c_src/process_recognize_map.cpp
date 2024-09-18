/*
	function:
		process decisive_battle map image for recognize
	parameters:
		Image absolute path
	compile command:
		g++ -o process_recognize_map process_recognize_map.cpp -I C:\Develop\opencv\opencv-4.5.4-mingw64\include -L C:\Develop\opencv\opencv-4.5.4-mingw64\lib -l libopencv_core454 -l libopencv_imgcodecs454
*/

#include "opencv2/opencv.hpp"
#include "module/image_function.h"

using namespace std;
using cv::Mat;
using cv::imread;
using cv::imwrite;
struct block{
	int left, right, top, bottom;
	void operator +=(const block &x){
			left=min(left, x.left);
			top=min(top, x.top);
			bottom=max(bottom, x.bottom);
			right=max(right, x.left);
	}
	bool operator ==(const block &x){
		return left == x.left && right == x.right && top == x.top && bottom == x.bottom;
	}
};
struct blocked_image{
	vector<vector<bool>> rec;
	vector<block> b, blocks;
	vector<int> fa;
	int row, col;
	int find_root(int x){
		return fa[x]==x?fa[x]:fa[x]=find_root(fa[x]);
	}
	void merge(int u,int v){
		u=find_root(u), v=find_root(v);
		if(u==v)return ;
		b[u]+=b[v], fa[v]=u;
	}
	int get_rk(int x, int y){
		return x * col + y;
	}
	void init(string image_path){
		Mat image = imread(image_path);
		row=image.rows, col=image.cols;
		rec.resize(row, vector<bool> (0)), blocks.clear();
		for(int i=0;i<row;i++){
			uchar* ptr=image.ptr<uchar>(i);
			for(int j=0;j<col;j++){
				const vector<vector<int>> COLOR_TEMPLATE({{225, 225, 225}});
				rec[i].push_back(is_key_color(ptr, COLOR_TEMPLATE, 30.0, 3));
				ptr+=3;
				// cout<<rec[i][j];
			}
			// cout<<'\n';
		}
		b.clear(), fa.clear();
		int size=row * col;
		rec.resize(size), fa.resize(size), b.resize(size);
		for(int i=0;i<row;i++){
			for(int j=0;j<col;j++){
				int rk=get_rk(i ,j);
				b[rk]=block{j, j, i, i};
				fa[rk]=rk;
				if(i&&rec[i-1][j]){
					merge(rk, get_rk(i - 1, j));
				}
				if(j&&rec[i][j-1]){
					merge(rk, get_rk(i, j - 1));
				}
			}
		}
		for(int i=0; i<size; i++)if(fa[i]==i&&b[i].left!=b[i].right){
			// cout<<i<<'\n';
			blocks.push_back(b[i]);
		}
	}
}img;
bool cmp(const block &a, const block &b){
	return a.top < b.top;
}

int main(int argc, char **args){
	img.init(args[1]);
	sort(img.blocks.begin(), img.blocks.end(), cmp);
	Mat M(img.row, img.col, CV_8UC1);
	for(int i=0; i<img.row; i++){
		for(int j=0; j<img.col; j++){
			int rk=img.get_rk(i, j);
			M.at<uchar>(i, j)=230 * bool(img.b[img.find_root(rk)]==img.blocks[0]);
			if(bool(img.b[img.find_root(rk)]==img.blocks[0])){
				// cout<<'#';
			}
			else{
				// cout<<'.';
			}
		}
		// cout<<'\n';
	}

	imwrite(string(args[1]), M);    //保存生成的图片
	return 0;
}
